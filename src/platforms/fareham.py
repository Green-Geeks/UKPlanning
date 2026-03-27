"""Fareham Borough Council CaseTracker scraper.

Custom ASP.NET application at fareham.gov.uk/casetrackerplanning.
Requires two-phase POST: first expand advanced search (postback),
then submit with dates using updated ViewState.
"""
import re
from datetime import date, datetime
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

BASE_URL = "https://www.fareham.gov.uk/casetrackerplanning"


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ["%d/%m/%Y", "%d %b %Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _extract_hidden_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    fields = {}
    for inp in soup.find_all("input", type="hidden"):
        name = inp.get("name", "")
        if name:
            fields[name] = inp.get("value", "")
    return fields


class FarehamScraper(BaseScraper):
    """Scraper for Fareham's CaseTracker planning portal."""

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=True,
            timeout=30,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        search_url = f"{BASE_URL}/applicationsearch.aspx"

        # Phase 1: GET initial page for ViewState
        resp = await self._client.get(search_url)
        fields = _extract_hidden_fields(resp.text)

        # Phase 2: POST to expand advanced search
        fields["__EVENTTARGET"] = "ctl00$BodyPlaceHolder$uxLinkButtonShowAdvancedSearch"
        fields["__EVENTARGUMENT"] = ""
        fields["ctl00$BodyPlaceHolder$uxTextSearchKeywords"] = ""

        resp = await self._client.post(search_url, data=fields)
        fields2 = _extract_hidden_fields(resp.text)

        # Phase 3: POST search with date range
        fields2["ctl00$BodyPlaceHolder$uxTextSearchKeywords"] = ""
        fields2["ctl00$BodyPlaceHolder$uxStartDateReceivedTextBox"] = date_from.strftime("%d/%m/%Y")
        fields2["ctl00$BodyPlaceHolder$uxStopDateReceivedTextBox"] = date_to.strftime("%d/%m/%Y")
        fields2["ctl00$BodyPlaceHolder$uxButtonSearch"] = "Search"

        resp = await self._client.post(search_url, data=fields2)

        # Parse results
        summaries = []
        for match in re.finditer(
            r'href="(ApplicationDetails\.aspx\?reference=([^&"]+)[^"]*)"',
            resp.text,
        ):
            url = match.group(1)
            ref = match.group(2).replace("%2f", "/").replace("%2F", "/")
            summaries.append(ApplicationSummary(
                uid=ref,
                url=f"{BASE_URL}/{url}",
            ))

        return summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        resp = await self._client.get(application.url)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        # Parse key fields from the concatenated text
        ref = application.uid
        address = ""
        description = ""
        status = ""

        # Pattern: "Reference{ref}Status{status}Proposal{desc}"
        ref_match = re.search(r"Address:\s*(.+?)(?=\n|Carry|Work|Erect|Construct|Demol|Propos|Install|Alter|Change|Variat|Extend|Remove|Retent|Outlin|Reserv|Full|Advert|List|Discharg|Prior|Appeal)", text)
        if ref_match:
            address = ref_match.group(1).strip()

        status_match = re.search(r"Status\s*(\w[\w\s]*?)(?=Proposal|$)", text)
        if status_match:
            status = status_match.group(1).strip()

        # The proposal is between "Proposal" and the next section
        desc_match = re.search(r"Proposal(?:Work To Tree Protected By TPO\s*)?(.+?)(?=Contact Us|How to|Useful|$)", text, re.S)
        if desc_match:
            description = desc_match.group(1).strip()[:500]

        return ApplicationDetail(
            reference=ref,
            address=address,
            description=description,
            url=application.url,
            status=status,
        )
