"""Civica Portal360 platform scraper.

Used by councils running Civica's planning portal with JSON API at Handler.ashx.
The search endpoint accepts date ranges and returns paginated KeyObjects with
application data in Items arrays of {FieldName, Value} pairs.
"""
from datetime import date, datetime
from typing import Dict, List, Optional

import httpx

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

COUNCIL_CONFIG = {
    "ashfield": {
        "handler": "https://planning.ashfield.gov.uk/civica/Resource/Civica/Handler.ashx",
        "ref_type": "GFPlanning",
        "app_url": "https://planning.ashfield.gov.uk/planning-applications/planning-application?RefType=GFPlanning&KeyNo=",
    },
    "stalbans": {
        "handler": "https://planningapplications.stalbans.gov.uk/w2webparts/Resource/Civica/Handler.ashx",
        "ref_type": "PBDC",
        "app_url": "https://planningapplications.stalbans.gov.uk/planning/planning-application?RefType=PBDC&KeyNo=",
    },
}

PAGE_SIZE = 10


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _field_dict(items: list) -> Dict[str, str]:
    return {
        i["FieldName"]: i["Value"]
        for i in items
        if i.get("FieldName") and i.get("Value") not in (None, "")
    }


class CivicaScraper(BaseScraper):
    """Scraper for Civica Portal360 planning portals with JSON API."""

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        cfg = COUNCIL_CONFIG.get(config.authority_code, {})
        self._handler_url = cfg.get("handler", "")
        self._ref_type = cfg.get("ref_type", "GFPlanning")
        self._app_url_base = cfg.get("app_url", "")
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "Content-Type": "application/json; charset=UTF-8",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=30,
        )

    async def _paged_search(self, search_fields: dict, from_row: int = 1) -> dict:
        body = {
            "refType": self._ref_type,
            "fromRow": from_row,
            "toRow": from_row + PAGE_SIZE - 1,
            "NoTotalRows": False,
            "searchFields": search_fields,
        }
        resp = await self._client.post(
            f"{self._handler_url}/keyobject/pagedsearch",
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        search_fields = {
            "received_dateFrom": date_from.strftime("%d/%m/%Y"),
            "received_dateTo": date_to.strftime("%d/%m/%Y"),
        }

        all_summaries = []
        from_row = 1
        total = None

        while True:
            data = await self._paged_search(search_fields, from_row)
            if total is None:
                total = data.get("TotalRows", 0)
            objects = data.get("KeyObjects", [])
            if not objects:
                break

            for obj in objects:
                fields = _field_dict(obj.get("Items", []))
                ref = fields.get("ref_no", "")
                key_no = obj.get("KeyNo") or fields.get("KeyNo", "")
                if ref:
                    all_summaries.append(ApplicationSummary(
                        uid=ref,
                        url=f"{self._app_url_base}{key_no}" if key_no else None,
                    ))

            from_row += PAGE_SIZE
            if from_row > total:
                break

        return all_summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        return ApplicationDetail(
            reference=application.uid,
            address="",
            description="",
            url=application.url,
        )

    async def scrape(self, date_from: date, date_to: date):
        from src.core.scraper import ScrapeResult
        try:
            search_fields = {
                "received_dateFrom": date_from.strftime("%d/%m/%Y"),
                "received_dateTo": date_to.strftime("%d/%m/%Y"),
            }

            details = []
            from_row = 1
            total = None

            while True:
                data = await self._paged_search(search_fields, from_row)
                if total is None:
                    total = data.get("TotalRows", 0)
                objects = data.get("KeyObjects", [])
                if not objects:
                    break

                for obj in objects:
                    fields = _field_dict(obj.get("Items", []))
                    ref = fields.get("ref_no", "")
                    if not ref:
                        continue
                    key_no = obj.get("KeyNo") or fields.get("KeyNo", "")
                    details.append(ApplicationDetail(
                        reference=ref,
                        address=fields.get("application_address", ""),
                        description=fields.get("proposal", ""),
                        url=f"{self._app_url_base}{key_no}" if key_no else None,
                        application_type=fields.get("app_type"),
                        status=fields.get("app_status"),
                        decision=fields.get("decision_notice_type"),
                        date_received=_parse_date(fields.get("received_date")),
                        date_validated=_parse_date(fields.get("valid_date")),
                        ward=fields.get("ward"),
                        parish=fields.get("parish"),
                        applicant_name=fields.get("ApplicantContactNoName"),
                        case_officer=fields.get("case_officer"),
                        raw_data=fields,
                    ))

                from_row += PAGE_SIZE
                if from_row > total:
                    break

            return ScrapeResult(date_from=date_from, date_to=date_to, applications=details)
        except Exception as e:
            return ScrapeResult(date_from=date_from, date_to=date_to, error=str(e))
