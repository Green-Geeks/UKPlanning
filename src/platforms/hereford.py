"""Herefordshire Council planning scraper.

Server-rendered search at herefordshire.gov.uk/planningapplicationsearch with
pagination via offset parameter (10 results per page). Detail pages at
/planningapplicationsearch/details?id={rawid}. Also has a REST search API at
restservices.herefordshire.gov.uk but the full application list and detail
data come from the main website.
"""
import re
from datetime import date, datetime
from typing import Dict, List, Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

BASE_URL = "https://www.herefordshire.gov.uk"
SEARCH_URL = f"{BASE_URL}/planningapplicationsearch"
DETAIL_URL = f"{SEARCH_URL}/details"
PAGE_SIZE = 10


def _parse_date(s: Optional[str]) -> Optional[date]:
    """Parse dates like 'Friday 20 March 2026' or '20/03/2026'."""
    if not s:
        return None
    s = s.strip()
    for fmt in ["%A %d %B %Y", "%d %B %Y", "%d/%m/%Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _clean_text(s: str) -> str:
    """Normalise whitespace and carriage returns from scraped text."""
    return re.sub(r"[\r\n\x0d]+", " ", s).strip()


def _clean_text_multi(s: str) -> str:
    """Normalise whitespace, collapsing runs of spaces."""
    return re.sub(r"\s+", " ", _clean_text(s))


class HerefordScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=True,
            timeout=30,
        )

    def _list_url(self, date_from: date, date_to: date, offset: int = 0) -> str:
        params = urlencode({
            "search-term": "e",
            "search-service": "search",
            "search-source": "the keyword",
            "search-item": "'e'",
            "date-from": date_from.strftime("%Y-%m-%d"),
            "date-to": date_to.strftime("%Y-%m-%d"),
            "status": "all",
            "offset": str(offset),
        })
        return f"{SEARCH_URL}?{params}"

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        summaries: List[ApplicationSummary] = []
        offset = 0
        max_recs = None

        while True:
            url = self._list_url(date_from, date_to, offset)
            resp = await self._client.get(url)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract total count from "Showing planning applications 1 to 10 of 101"
            if max_recs is None:
                notif = soup.find("div", class_=re.compile(r"hc-notification--info"))
                if notif:
                    count_match = re.search(r"of\s+(\d+)\s+for", notif.get_text())
                    if count_match:
                        max_recs = int(count_match.group(1))

            # Extract application links from results table
            page_count = 0
            for link in soup.find_all("a", href=re.compile(r"details\?id=\d+")):
                href = link.get("href", "")
                uid = link.get_text(strip=True)
                if not uid:
                    continue
                rawid_match = re.search(r"id=(\d+)", href)
                if not rawid_match:
                    continue
                rawid = rawid_match.group(1)
                detail_url = f"{DETAIL_URL}?id={rawid}"
                summaries.append(ApplicationSummary(uid=uid, url=detail_url))
                page_count += 1

            if page_count == 0:
                break

            offset += PAGE_SIZE

            # Stop if we have all results
            if max_recs is not None and len(summaries) >= max_recs:
                break

            # Safety cap at 500 pages (5000 results)
            if offset > 5000:
                break

        return summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        # The detail page needs a search-term param to work
        url = application.url
        if "search-term" not in url:
            sep = "&" if "?" in url else "?"
            search_params = urlencode({
                "search-term": "e",
                "search-service": "search",
                "search-source": "the keyword",
                "search-item": "'e'",
            })
            url = f"{url}{sep}{search_params}"

        resp = await self._client.get(url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        fields = self._extract_fields(soup)

        easting = None
        northing = None
        en = fields.get("Easting/Northing", "")
        en_match = re.match(r"(\d+)\s*-\s*(\d+)", en)
        if en_match:
            easting = en_match.group(1)
            northing = en_match.group(2)

        return ApplicationDetail(
            reference=fields.get("Number", application.uid),
            address=_clean_text_multi(fields.get("Location", "")),
            description=_clean_text_multi(fields.get("Proposal", "")),
            url=application.url,
            application_type=_clean_text(fields.get("Type", "")),
            status=_clean_text(fields.get("Current status", "")),
            decision=_clean_text(fields.get("Decision", "")),
            date_received=_parse_date(fields.get("Date received")),
            date_validated=_parse_date(fields.get("Date validated")),
            ward=_clean_text(fields.get("Ward", "")),
            parish=_clean_text(fields.get("Parish", "")),
            applicant_name=_clean_text_multi(fields.get("Applicant address", "")),
            case_officer=_clean_text(fields.get("Case officer", "")),
            raw_data={
                **fields,
                **({"easting": easting, "northing": northing} if easting else {}),
            },
        )

    def _extract_fields(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract th/td pairs from detail page tables."""
        fields: Dict[str, str] = {}
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    label = th.get_text(strip=True)
                    # For the Location field, get text from nested link
                    link = td.find("a")
                    value = link.get_text(strip=True) if link and label == "Location" else td.get_text(strip=True)
                    if label:
                        fields[label] = value
        return fields

