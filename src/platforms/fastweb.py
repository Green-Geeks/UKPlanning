"""Fastweb platform scraper (Rotherham, Wokingham).

POST to /results.asp with DateReceivedStart/End. Results as HTML table
with detail links at /detail.asp?AltRef={ref}.
"""
import re
from datetime import date, datetime
from typing import List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

COUNCIL_URLS = {
    "rotherham": "https://planning.rotherham.gov.uk/fastweblive",
    "wokingham": "https://planning.wokingham.gov.uk/FastWebPL",
}


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


class FastwebScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._base_url = COUNCIL_URLS.get(
            config.authority_code, config.base_url.rstrip("/")
        )
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=True,
            timeout=30,
            verify=False,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        resp = await self._client.post(f"{self._base_url}/results.asp", data={
            "DateReceivedStart": date_from.strftime("%d/%m/%Y"),
            "DateReceivedEnd": date_to.strftime("%d/%m/%Y"),
        })
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        summaries = []
        seen = set()

        for link in soup.find_all("a", href=re.compile(r"detail\.asp")):
            href = link.get("href", "")
            ref_match = re.search(r"AltRef=([^&]+)", href)
            if not ref_match:
                continue
            ref = ref_match.group(1)
            if ref in seen:
                continue
            seen.add(ref)
            full_url = urljoin(f"{self._base_url}/", href)
            summaries.append(ApplicationSummary(uid=ref, url=full_url))

        return summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        resp = await self._client.get(application.url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        fields = {}

        # Fastweb uses label/value in table cells or dt/dd
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).rstrip(":").strip()
                    value = cells[1].get_text(strip=True)
                    if label and value:
                        fields[label] = value

        return ApplicationDetail(
            reference=fields.get("Reference", fields.get("Planning Application Number", fields.get("Application Number", application.uid))),
            address=fields.get("Site Address", fields.get("Location", fields.get("Address", ""))),
            description=fields.get("Description", fields.get("Proposal", "")),
            url=application.url,
            application_type=fields.get("Application Type"),
            status=fields.get("Status", fields.get("Decision")),
            date_received=_parse_date(fields.get("Date Received", "")),
            date_validated=_parse_date(fields.get("Date Valid", "")),
            ward=fields.get("Ward"),
            parish=fields.get("Parish"),
            case_officer=fields.get("Case Officer"),
        )
