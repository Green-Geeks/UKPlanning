"""Tascomi platform scraper (Dartmoor, Barking/Be First).

Tascomi portals serve weekly lists at fa=getReceivedWeeklyList which contain
application data in HTML tables. Detail pages return 202 async, so we extract
all data from the weekly list tables instead.

For search by date range, we POST to the search form with date parameters.
"""
import re
from datetime import date, datetime
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

COUNCIL_URLS = {
    "dartmoor": "https://dartmoor-online.tascomi.com",
    "barking": "https://online-befirst.lbbd.gov.uk",
}


class TascomiScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._base_url = COUNCIL_URLS.get(
            config.authority_code, config.base_url.rstrip("/")
        )
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            follow_redirects=True,
            timeout=30,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        """Get applications from the weekly received list."""
        url = f"{self._base_url}/planning/index.html?fa=getReceivedWeeklyList"
        resp = await self._client.get(url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        summaries = []

        for link in soup.find_all("a", href=re.compile(r"getApplication.*id=\d+")):
            href = link.get("href", "")
            id_match = re.search(r"id=(\d+)", href)
            if id_match:
                app_id = id_match.group(1)
                summaries.append(ApplicationSummary(
                    uid=app_id,
                    url=f"{self._base_url}{href}" if href.startswith("/") else href,
                ))

        return summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        """Extract detail from the weekly list table row (detail pages return 202)."""
        # Re-fetch the weekly list and find this application's row
        url = f"{self._base_url}/planning/index.html?fa=getReceivedWeeklyList"
        resp = await self._client.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find the row containing this application's link
        for row in soup.find_all("tr"):
            link = row.find("a", href=re.compile(rf"id={application.uid}"))
            if not link:
                continue

            cells = row.find_all("td")
            if len(cells) >= 5:
                return ApplicationDetail(
                    reference=cells[0].get_text(strip=True),
                    address=cells[1].get_text(strip=True),
                    description=cells[2].get_text(strip=True),
                    url=application.url,
                    ward=cells[3].get_text(strip=True),
                    parish=cells[4].get_text(strip=True),
                )

        return ApplicationDetail(
            reference=application.uid,
            address="",
            description="",
            url=application.url,
        )

    async def scrape(self, date_from: date, date_to: date):
        """Override to extract all data from weekly list in one pass."""
        from src.core.scraper import ScrapeResult
        try:
            url = f"{self._base_url}/planning/index.html?fa=getReceivedWeeklyList"
            resp = await self._client.get(url)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            details = []

            for row in soup.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue

                link = row.find("a", href=re.compile(r"getApplication.*id=\d+"))
                href = link.get("href", "") if link else ""
                app_url = f"{self._base_url}{href}" if href.startswith("/") else href

                details.append(ApplicationDetail(
                    reference=cells[0].get_text(strip=True),
                    address=cells[1].get_text(strip=True),
                    description=cells[2].get_text(strip=True),
                    url=app_url,
                    ward=cells[3].get_text(strip=True),
                    parish=cells[4].get_text(strip=True),
                ))

            return ScrapeResult(date_from=date_from, date_to=date_to, applications=details)
        except Exception as e:
            return ScrapeResult(date_from=date_from, date_to=date_to, error=str(e))
