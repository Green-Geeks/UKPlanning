"""Barnsley Metropolitan Borough Council Planning Explorer scraper.

Custom portal at planningexplorer.barnsley.gov.uk with weekly/monthly/yearly
list endpoints and detail pages at /Home/ApplicationDetails.
"""
import re
from datetime import date, datetime
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

BASE_URL = "https://planningexplorer.barnsley.gov.uk"


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ["%d %B %Y", "%d/%m/%Y", "%d %b %Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


class BarnsleyScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=True,
            timeout=30,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        # Use the appropriate time range endpoint
        days = (date_to - date_from).days
        if days <= 7:
            path = "/Home/ShowLastWeekPlanningApplications"
        elif days <= 30:
            path = "/Home/ShowLastMonthPlanningApplications"
        else:
            path = "/Home/ShowLastYearPlanningApplications"

        resp = await self._client.get(f"{BASE_URL}{path}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        summaries = []

        for link in soup.find_all("a", href=re.compile(r"ApplicationDetails")):
            href = link.get("href", "")
            ref = link.get_text(strip=True)
            if ref:
                summaries.append(ApplicationSummary(
                    uid=ref,
                    url=f"{BASE_URL}{href}" if href.startswith("/") else href,
                ))

        return summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        resp = await self._client.get(application.url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        def extract(label: str) -> str:
            match = re.search(rf"{label}\s*\n\s*(.+)", text)
            return match.group(1).strip() if match else ""

        # Also try from table rows on list page
        # The detail page may have dt/dd or label/value pairs
        detail = {}
        for dt in soup.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                detail[dt.get_text(strip=True)] = dd.get_text(strip=True)

        return ApplicationDetail(
            reference=application.uid,
            address=detail.get("Site Address", detail.get("Address", extract("Site Address"))),
            description=detail.get("Proposal", detail.get("Description", extract("Description"))),
            url=application.url,
            status=detail.get("Status", extract("Status")),
            decision=detail.get("Decision", extract("Decision")),
            date_received=_parse_date(detail.get("Validated Date", extract("Validated Date"))),
            ward=detail.get("Ward", extract("Ward")),
            parish=detail.get("Parish", extract("Parish")),
        )
