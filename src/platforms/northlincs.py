"""North Lincolnshire Council planning portal scraper.

Simple GET-based search at apps.northlincs.gov.uk with start_date/end_date params.
Detail pages at /application/{slug} with clean HTML structure.
"""
import re
from datetime import date, datetime
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

BASE_URL = "https://apps.northlincs.gov.uk"


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ["%d %B %Y", "%d/%m/%Y", "%d %b %Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


class NorthLincsScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=True,
            timeout=30,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        resp = await self._client.get(f"{BASE_URL}/search", params={
            "start_date": date_from.strftime("%d/%m/%Y"),
            "end_date": date_to.strftime("%d/%m/%Y"),
        })
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        summaries = []
        seen = set()

        for link in soup.find_all("a", href=re.compile(r"/application/")):
            href = link.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            slug = href.split("/application/")[-1]
            summaries.append(ApplicationSummary(
                uid=slug,
                url=f"{BASE_URL}{href}" if href.startswith("/") else href,
            ))

        return summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        resp = await self._client.get(application.url)
        resp.raise_for_status()

        # Extract the Application Details section
        section_match = re.search(
            r"Application Details(.+?)Related Documents", resp.text, re.S
        )
        if not section_match:
            return ApplicationDetail(
                reference=application.uid, address="", description="",
                url=application.url,
            )

        section = BeautifulSoup(section_match.group(1), "html.parser")
        lines = [l.strip() for l in section.get_text("\n", strip=True).split("\n") if l.strip()]

        def extract(label: str) -> str:
            for i, line in enumerate(lines):
                if line == label and i + 1 < len(lines):
                    return lines[i + 1]
            return ""

        address_parts = []
        in_location = False
        for i, line in enumerate(lines):
            if line == "Site Location":
                in_location = True
                continue
            if in_location:
                if line in ("Parish", "Ward", "Case Officer"):
                    break
                address_parts.append(line)

        return ApplicationDetail(
            reference=extract("Reference"),
            address=", ".join(address_parts),
            description=extract("Proposed Development"),
            url=application.url,
            date_received=_parse_date(extract("Date Valid")),
            ward=extract("Ward"),
            parish=extract("Parish"),
            case_officer=extract("Officer Name"),
            decision=extract("Decision") or None,
        )
