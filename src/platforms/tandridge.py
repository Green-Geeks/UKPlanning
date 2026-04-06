"""Tandridge District Council planning scraper.

Custom ASP.NET with dropdown postback. Three-phase:
1. GET page for ViewState
2. POST to select "Acknowledged date" dropdown
3. POST with YYYY-MM-DD dates to search

Results in HTML table: Application number, Address, Description, Parish, Comments until.
"""
import re
from datetime import date
from typing import List

import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper, ScrapeResult

BASE_URL = "https://tdcplanningsearch.tandridge.gov.uk/"


def _extract_hidden(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    return {inp.get("name", ""): inp.get("value", "")
            for inp in soup.find_all("input", type="hidden") if inp.get("name")}


class TandridgeScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=True, timeout=30, verify=False,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        return []  # Use scrape() override instead

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        return ApplicationDetail(reference=application.uid, address="", description="", url=application.url)

    async def scrape(self, date_from: date, date_to: date) -> ScrapeResult:
        try:
            # Phase 1: GET
            resp = await self._client.get(BASE_URL)
            fields = _extract_hidden(resp.text)

            # Phase 2: dropdown postback
            fields["__EVENTTARGET"] = "ctl00$MainContent$ddlSearchCriteria"
            fields["ctl00$MainContent$ddlSearchCriteria"] = "Acknowledged date"
            resp2 = await self._client.post(BASE_URL, data=fields)
            fields2 = _extract_hidden(resp2.text)

            # Phase 3: search
            fields2["ctl00$MainContent$ddlSearchCriteria"] = "Acknowledged date"
            fields2["ctl00$MainContent$txtStartDate"] = date_from.isoformat()
            fields2["ctl00$MainContent$txtEndDate"] = date_to.isoformat()
            fields2["ctl00$MainContent$btnSearch"] = "Search"
            resp3 = await self._client.post(BASE_URL, data=fields2)

            soup = BeautifulSoup(resp3.text, "html.parser")
            details = []

            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                if len(rows) < 2:
                    continue
                headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
                if "application" not in " ".join(headers):
                    continue

                for row in rows[1:]:
                    cells = row.find_all("td")
                    if len(cells) < 3:
                        continue
                    details.append(ApplicationDetail(
                        reference=cells[0].get_text(strip=True),
                        address=cells[1].get_text(strip=True) if len(cells) > 1 else "",
                        description=cells[2].get_text(strip=True) if len(cells) > 2 else "",
                        url=BASE_URL,
                        parish=cells[3].get_text(strip=True) if len(cells) > 3 else "",
                    ))

            return ScrapeResult(date_from=date_from, date_to=date_to, applications=details)
        except Exception as e:
            return ScrapeResult(date_from=date_from, date_to=date_to, error=str(e))
