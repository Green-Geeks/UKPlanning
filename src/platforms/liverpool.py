"""LAR (Licensing and Regulations) platform scraper.

Used by Liverpool, Rother, and potentially other councils.
Uses POST to /planning/index.html with fa=getApplications for search results.
Results are returned in a server-rendered HTML table.
"""
from datetime import date
from typing import List

from bs4 import BeautifulSoup

from src.core.browser import HttpClient
from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper


class LiverpoolScraper(BaseScraper):
    """LAR platform scraper. Uses config.base_url to support multiple councils."""

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._base_url = config.base_url.rstrip("/")
        self._client = HttpClient(timeout=30, rate_limit_delay=config.rate_limit_delay)

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        response = await self._client.post(
            f"{self._base_url}/planning/index.html",
            data={
                "fa": "getApplications",
                "received_date_from": date_from.strftime("%d/%m/%Y"),
                "received_date_to": date_to.strftime("%d/%m/%Y"),
            },
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        table = soup.find("table")
        if not table:
            return []

        results = []
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 7:
                continue
            ref = cells[0].get_text(strip=True)
            app_type = cells[1].get_text(strip=True)
            address = cells[2].get_text(strip=True)
            description = cells[3].get_text(strip=True)
            ward = cells[4].get_text(strip=True)
            community = cells[5].get_text(strip=True)
            decision = cells[6].get_text(strip=True)

            btn = row.find("button", class_="view_application")
            data_id = btn.get("data-id", "") if btn else ""

            results.append(ApplicationSummary(
                uid=ref,
                url=f"{self._base_url}/planning/index.html?fa=getApplication&id={data_id}" if data_id else None,
            ))
            results[-1]._extra = {
                "app_type": app_type,
                "address": address,
                "description": description,
                "ward": ward,
                "community": community,
                "decision": decision,
                "data_id": data_id,
            }

        return results

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        extra = getattr(application, "_extra", {})
        return ApplicationDetail(
            reference=application.uid,
            address=extra.get("address", ""),
            description=extra.get("description", ""),
            url=application.url or "",
            application_type=extra.get("app_type"),
            status=extra.get("decision") or None,
            ward=extra.get("ward"),
            parish=extra.get("community"),
            raw_data=extra,
        )
