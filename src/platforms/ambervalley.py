"""Amber Valley Council planning scraper.

Custom JSON API at info.ambervalley.gov.uk/WebServices/AVBCFeeds/DevConJSON.asmx.
Search by date range via PlanAppsByAddressKeyword (filters on dateValid),
then fetch full details via GetPlanAppDetails.
"""
from datetime import date, datetime
from typing import List, Optional

import httpx

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

API_BASE = "https://info.ambervalley.gov.uk/WebServices/AVBCFeeds/DevConJSON.asmx"
PORTAL_URL = "https://www.ambervalley.gov.uk/planning/development-management/view-a-planning-application/"


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s or s.startswith("0001-01-01"):
        return None
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, AttributeError):
        return None


class AmberValleyScraper(BaseScraper):
    """Scraper for Amber Valley's JSON planning API."""

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=30,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        resp = await self._client.post(
            f"{API_BASE}/PlanAppsByAddressKeyword",
            data={
                "keyWord": "",
                "fromDate": date_from.strftime("%d/%m/%Y"),
                "toDate": date_to.strftime("%d/%m/%Y"),
            },
        )
        resp.raise_for_status()
        records = resp.json()
        if not isinstance(records, list):
            return []

        return [
            ApplicationSummary(
                uid=r.get("refVal", ""),
                url=f"{PORTAL_URL}?refVal={r.get('refVal', '')}",
            )
            for r in records
            if r.get("refVal")
        ]

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        resp = await self._client.get(
            f"{API_BASE}/GetPlanAppDetails",
            params={"refVal": application.uid},
        )
        resp.raise_for_status()
        data = resp.json()

        address = (data.get("applicationAddress") or "").replace("\r", ", ")

        return ApplicationDetail(
            reference=data.get("refVal", application.uid),
            address=address,
            description=data.get("proposal", ""),
            url=application.url,
            application_type=data.get("applicationTypeCode"),
            status=data.get("status"),
            decision=data.get("decision"),
            date_received=_parse_date(data.get("dateReceived")),
            date_validated=_parse_date(data.get("dateValid")),
            ward=data.get("wardName"),
            parish=None,
            applicant_name=data.get("applicantName"),
            case_officer=data.get("officerName"),
            raw_data=data,
        )
