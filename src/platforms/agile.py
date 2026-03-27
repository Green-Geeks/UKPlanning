"""Agile Applications (IEG4) platform scraper.

Used by ~9 UK councils via planning.agileapplications.co.uk.
All councils share the same API at planningapi.agileapplications.co.uk
differentiated by x-client header containing the council code.

The search endpoint requires a reference prefix or keyword to narrow results.
We search by year prefix (e.g. "R26/" for Rugby 2026) and filter by date.
"""
from datetime import date, datetime
from typing import List, Optional

import httpx

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

API_BASE = "https://planningapi.agileapplications.co.uk/api"
PORTAL_BASE = "https://planning.agileapplications.co.uk"

# Map authority_code to API client code and reference prefix pattern
COUNCIL_CONFIG = {
    "exmoor": {"client": "EXMOOR", "prefix": "ENP"},
    "flintshire": {"client": "FLINTSHIRE", "prefix": "FUL"},
    "islington": {"client": "ISLINGTON", "prefix": "P20"},
    "middlesbrough": {"client": "MIDDLESBROUGH", "prefix": "M/"},
    "pembrokecoast": {"client": "PCNPA", "prefix": "NP/"},
    "rugby": {"client": "RUGBY", "prefix": "R"},
    "slough": {"client": "SLOUGH", "prefix": "P/"},
    "staffordshire": {"client": "STAFFORDSHIRE", "prefix": "SS."},
    "yorkshiredales": {"client": "YORKSHIREDALES", "prefix": "C/"},
    "richmond": {"client": "RICHMONDUPONTHAMES", "prefix": "PA"},
}


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


class AgileApplicationsScraper(BaseScraper):
    """Scraper for the Agile Applications (IEG4) planning portal API."""

    PAGE_SIZE = 100

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        council_cfg = COUNCIL_CONFIG.get(config.authority_code, {})
        self._client_code = council_cfg.get("client", config.authority_code.upper())
        self._prefix = council_cfg.get("prefix", "")
        self._portal_url = config.base_url or f"{PORTAL_BASE}/{config.authority_code}"
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "x-client": self._client_code,
                "x-service": "PA",
                "x-product": "CITIZENPORTAL",
            },
            timeout=30,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        """Search for applications by registration date range."""
        all_summaries = []
        page = 1

        while True:
            resp = await self._client.get("/application/search", params={
                "registrationDateFrom": date_from.isoformat(),
                "registrationDateTo": date_to.isoformat(),
                "page": page,
                "pageSize": self.PAGE_SIZE,
            })
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, list) and data and data[0].get("code"):
                break  # Error response

            results = data.get("results", [])
            if not results:
                break

            for item in results:
                app_id = str(item["id"])
                all_summaries.append(ApplicationSummary(
                    uid=app_id,
                    url=f"{self._portal_url}/application-details/{app_id}",
                ))

            total = data.get("total", 0)
            if page * self.PAGE_SIZE >= total:
                break
            page += 1

        return all_summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        """Fetch full application details from the API."""
        resp = await self._client.get(f"/application/{application.uid}")
        resp.raise_for_status()
        data = resp.json()

        return ApplicationDetail(
            reference=data.get("reference", ""),
            address=data.get("location", ""),
            description=data.get("fullProposal") or data.get("proposal", ""),
            url=application.url,
            application_type=data.get("applicationType"),
            status=data.get("statusDescription"),
            decision=data.get("decisionText"),
            date_received=_parse_date(data.get("receivedDate")),
            date_validated=_parse_date(data.get("validDate")),
            ward=data.get("ward"),
            parish=data.get("parish"),
            applicant_name=data.get("applicantSurname"),
            case_officer=data.get("officerName"),
            raw_data=data,
        )
