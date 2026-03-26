"""Northern Ireland Planning Portal scraper.

All 11 NI councils share a single planning portal at planningsystemni.gov.uk.
The portal exposes a JSON API at api-planningregister-planningportal.pr.tqinfra.co.uk.

Each council is identified by an authorityId in the API. Applications are searched
via SearchTerm and filtered by authority. Detail is fetched per applicationId.
"""
from datetime import date, datetime
from typing import Dict, List, Optional

import httpx

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

API_BASE = "https://api-planningregister-planningportal.pr.tqinfra.co.uk/api/v1"
TENANT_ID = "cfb86436-414d-4459-9545-93eec37615a2"
PORTAL_BASE = "https://planningregister.planningsystemni.gov.uk"

# Map our authority_code to the NI API's authorityId
AUTHORITY_MAP = {
    "antrimnewtownabbey": 1,
    "ardsnorthdown": 2,
    "armaghbanbridgecraigavon": 3,
    "belfast": 4,
    "causewayglens": 5,
    "derrystrabane": 6,
    "fermanaghomagh": 7,
    "lisburncastlereagh": 8,
    "mideastantrim": 9,
    "newrymournedown": 10,
}

# Map authorityId -> LA reference prefix for search
# Some councils use multiple prefixes; we search the primary one
# and filter by authorityId in the response
AUTHORITY_PREFIX = {
    1: "LA03",   # Antrim and Newtownabbey
    2: "LA06",   # Ards and North Down
    3: "LA08",   # Armagh, Banbridge and Craigavon
    4: "LA04",   # Belfast
    5: "LA01",   # Causeway Coast and Glens
    6: "LA11",   # Derry and Strabane
    7: "LA09",   # Fermanagh and Omagh (primary)
    8: "LA05",   # Lisburn and Castlereagh
    9: "LA02",   # Mid and East Antrim
    10: "LA07",  # Newry, Mourne and Down (primary)
}

# Councils with multiple LA prefixes
EXTRA_PREFIXES = {
    7: ["LA10"],   # Fermanagh and Omagh also uses LA10
    10: ["LA12"],  # Newry, Mourne and Down also uses LA12
}


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


class NIPortalScraper(BaseScraper):
    """Scraper for the Northern Ireland Planning Portal API."""

    PAGE_SIZE = 100

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._authority_id = AUTHORITY_MAP.get(config.authority_code)
        primary = AUTHORITY_PREFIX.get(self._authority_id, "")
        extras = EXTRA_PREFIXES.get(self._authority_id, [])
        self._prefixes = [primary] + extras if primary else []
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "TQ-Tenant": TENANT_ID,
            },
            timeout=30,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        """Search for applications by reference prefix and filter by date."""
        if not self._prefixes:
            return []

        all_summaries = []
        seen_ids = set()

        for prefix in self._prefixes:
            page = 1
            while True:
                params = {
                    "SearchTerm": prefix,
                    "PageSize": self.PAGE_SIZE,
                    "PageNumber": page,
                    "SortBy": "DateReceived",
                    "SortByAscending": "false",
                }

                resp = await self._client.get("/applications", params=params)
                resp.raise_for_status()
                data = resp.json()

                items = data.get("applications", {}).get("items", [])
                if not items:
                    break

                past_range = False
                for item in items:
                    received = _parse_date(item.get("dateReceived"))
                    if received and received < date_from:
                        past_range = True
                        break
                    if received and date_from <= received <= date_to:
                        if self._authority_id and item.get("authorityId") != self._authority_id:
                            continue
                        app_id = str(item["applicationId"])
                        if app_id not in seen_ids:
                            seen_ids.add(app_id)
                            all_summaries.append(ApplicationSummary(
                                uid=app_id,
                                url=f"{PORTAL_BASE}/application/{app_id}",
                            ))

                if past_range or len(items) < self.PAGE_SIZE:
                    break
                page += 1

        return all_summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        """Fetch full application details from the API."""
        resp = await self._client.get(f"/application/{application.uid}")
        resp.raise_for_status()
        data = resp.json()

        return ApplicationDetail(
            reference=data.get("applicationReferenceNumber", ""),
            address=data.get("siteAddress", ""),
            description=data.get("proposalText", ""),
            url=application.url,
            application_type=data.get("applicationType"),
            status=data.get("applicationStatus"),
            decision=data.get("decisionType"),
            date_received=_parse_date(data.get("dateReceived")),
            date_validated=_parse_date(data.get("dateValidated")),
            ward=data.get("ward"),
            parish=data.get("districtElectoralArea"),
            applicant_name=data.get("applicantName"),
            case_officer=None,
            raw_data=data,
        )
