"""Statmap HorizoNext platform scraper.

Used by East Staffordshire, West Lindsey, North York Moors, and potentially others.
Clean JSON API at /horizoNext/api/publicportal/planningApplications/pageRequest.
No authentication required for public endpoints.
"""
import json
from datetime import date, datetime
from typing import Dict, List, Optional

import httpx

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

COUNCIL_URLS = {
    "eaststaffordshire": "https://eaststaffs-publicportal.statmap.co.uk",
    "westlindsey": "https://westlindsey-publicportal.statmap.co.uk",
    "northyorkmoors": "https://northyorkmoors-publicportal.statmap.co.uk",
}


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


class StatmapScraper(BaseScraper):

    PAGE_SIZE = 50

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._base_url = COUNCIL_URLS.get(
            config.authority_code, config.base_url.rstrip("/")
        )
        self._api_url = f"{self._base_url}/horizoNext/api/publicportal"
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "Content-Type": "application/json",
            },
            timeout=30,
            verify=False,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        all_results = []
        offset = 0

        while True:
            body = {
                "filter": {
                    "parts": [{
                        "filterItems": [
                            {"columnName": "receivedDate", "operator": "onOrAfter", "value": date_from.isoformat()},
                            {"columnName": "receivedDate", "operator": "onOrBefore", "value": date_to.isoformat()},
                        ]
                    }]
                },
                "offset": offset,
                "order": {"receivedDate": "desc"},
                "select": "",
                "pageSize": self.PAGE_SIZE,
            }

            resp = await self._client.post(
                f"{self._api_url}/planningApplications/pageRequest",
                content=json.dumps(body),
            )
            resp.raise_for_status()
            data = resp.json()

            records = data.get("records", [])
            if not records:
                break

            page_had_results = False
            for record in records:
                received = _parse_date(record.get("receivedDate"))
                if received and (received < date_from or received > date_to):
                    continue
                page_had_results = True
                app_id = str(record.get("id", ""))
                ref = record.get("name", "")
                all_results.append(ApplicationSummary(uid=ref or app_id, url=app_id))
                all_results[-1]._record = record

            if not page_had_results:
                break
            offset += self.PAGE_SIZE

        return all_results

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        record = getattr(application, "_record", None)
        if not record:
            resp = await self._client.get(
                f"{self._api_url}/planningApplications/{application.url}"
            )
            resp.raise_for_status()
            record = resp.json()

        app_type_rel = record.get("applicationTypeId_relatedRecord") or {}
        detail_url = f"{self._base_url}/horizoNext/publicportal#/planningApplication/{record.get('id', '')}"

        return ApplicationDetail(
            reference=record.get("name", "") or application.uid,
            address=record.get("address", ""),
            description=record.get("proposal", ""),
            url=detail_url,
            application_type=app_type_rel.get("name"),
            status=record.get("status"),
            decision=record.get("decision"),
            date_received=_parse_date(record.get("receivedDate")),
            date_validated=_parse_date(record.get("validDate")),
            ward=record.get("ward"),
            parish=record.get("parish"),
            applicant_name=record.get("applicantName"),
            case_officer=record.get("caseOfficer"),
            raw_data=record,
        )
