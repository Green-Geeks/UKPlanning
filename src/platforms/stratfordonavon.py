"""Stratford-on-Avon District Council ePlanning v2 scraper.

Vue 3 + Axios frontend backed by a REST API at
https://apps.stratford.gov.uk/EplanningV2/API/v1/Search.
Search endpoint accepts query params and returns JSON array of applications.
No authentication required for public search.
"""
from datetime import date, datetime
from typing import Dict, List, Optional

import httpx

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

API_URL = "https://apps.stratford.gov.uk/EplanningV2/API/v1/Search"


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ["%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


class StratfordOnAvonScraper(BaseScraper):
    """Scraper for Stratford-on-Avon's ePlanning v2 REST API."""

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=True,
            timeout=30,
        )
        self._cache: Dict[str, Dict] = {}

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        params = {
            "dateAppReceivedFrom": date_from.isoformat(),
            "dateAppReceivedTo": date_to.isoformat(),
        }

        resp = await self._client.get(API_URL, params=params)
        resp.raise_for_status()
        results = resp.json()

        summaries = []
        for app in results:
            ref = app.get("reference", "")
            link = app.get("link", "")
            if ref:
                self._cache[ref] = app
                summaries.append(ApplicationSummary(uid=ref, url=link))
        return summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        """Build detail from cached search results.

        The search API already returns all fields (reference, address,
        proposal, status, dates). The detail page is Vue-rendered
        client-side so we use the cached JSON data directly.
        """
        app = self._cache.get(application.uid)
        if not app:
            return ApplicationDetail(
                reference=application.uid,
                address="",
                description="",
                url=application.url,
            )
        return self._parse_application(app)

    @staticmethod
    def _parse_application(app: Dict) -> ApplicationDetail:
        return ApplicationDetail(
            reference=app.get("reference", ""),
            address=app.get("address", "").strip(),
            description=app.get("proposal", "").strip(),
            url=app.get("link", ""),
            status=app.get("status"),
            date_received=_parse_date(app.get("validDate", "")),
            date_validated=_parse_date(app.get("validDate", "")),
            decision=app.get("decisionDate"),
            raw_data=app,
        )
