"""Bath and North East Somerset (BANES) planning scraper.

JSON API at api.bathnes.gov.uk/webapi/api/PlanningAPI/v2/planningdata/search/
Uses application_isharedate_from/to for date-based search.
"""
from datetime import date, datetime
from typing import List, Optional

import httpx

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

API_URL = "https://api.bathnes.gov.uk/webapi/api/PlanningAPI/v2/planningdata/search/"
PORTAL_URL = "https://app.bathnes.gov.uk/webforms/planning/details.html"


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.split("T")[0]).date()
    except (ValueError, AttributeError):
        return None


class BathScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=30,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        resp = await self._client.post(API_URL, json={
            "application_isharedate_from": date_from.isoformat(),
            "application_isharedate_to": date_to.isoformat(),
        }, headers={"Content-Type": "application/json"})
        resp.raise_for_status()

        data = resp.json()
        if not isinstance(data, list):
            return []

        return [
            ApplicationSummary(
                uid=item.get("refval", ""),
                url=f"{PORTAL_URL}?refval={item.get('refval', '')}",
            )
            for item in data
            if item.get("refval")
        ]

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        # Search by reference to get full detail
        resp = await self._client.post(API_URL, json={
            "refval_address": application.uid,
        }, headers={"Content-Type": "application/json"})
        resp.raise_for_status()

        data = resp.json()
        item = data[0] if isinstance(data, list) and data else {}

        return ApplicationDetail(
            reference=item.get("refval", application.uid),
            address=item.get("addressline", ""),
            description=item.get("proposal", ""),
            url=application.url,
            application_type=item.get("dcapptyp_text"),
            status=item.get("dcstat_text"),
            decision=item.get("datedecisn"),
            date_received=_parse_date(item.get("dateaprecv")),
            date_validated=_parse_date(item.get("dateapval")),
            ward=item.get("ward_text"),
            parish=item.get("parish_text"),
            raw_data=item,
        )
