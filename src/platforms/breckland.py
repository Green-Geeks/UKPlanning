"""Breckland Council planning scraper - Ocella2 platform.

Ocella2 portals use a form named 'OcellaPlanningSearch' with date fields
receivedFrom/receivedTo (format dd-mm-yy) and a 'showall' checkbox.
Results are returned as a single HTML page with a table of application links.
Detail pages use td label/value pairs.

URL: https://planning.breckland.gov.uk/OcellaWeb/planningSearch
"""

import re
from datetime import date, datetime
from typing import List, Optional
from urllib.parse import urljoin, quote_plus

from bs4 import BeautifulSoup

from src.core.browser import HttpClient
from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

SEARCH_URL = "https://planning.breckland.gov.uk/OcellaWeb/planningSearch"
DETAIL_PATH = "planningDetails"

DATE_FORMAT_REQUEST = "%d-%m-%y"


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d-%m-%y", "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _cell_text(row, index: int) -> str:
    """Extract text from the Nth td in a table row."""
    cells = row.find_all("td")
    if index < len(cells):
        return cells[index].get_text(strip=True)
    return ""


def _extract_detail_field(soup: BeautifulSoup, label: str) -> Optional[str]:
    """Find a td containing `label` and return the text of the next td sibling."""
    for td in soup.find_all("td"):
        if td.get_text(strip=True) == label:
            next_td = td.find_next_sibling("td")
            if next_td:
                text = next_td.get_text(strip=True)
                return text if text else None
    return None


class BrecklandScraper(BaseScraper):
    """Scraper for Breckland's Ocella2 planning portal."""

    FORM_NAME = "OcellaPlanningSearch"

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._base_url = config.base_url or SEARCH_URL
        self._client = HttpClient(
            timeout=60,
            rate_limit_delay=config.rate_limit_delay,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        # GET the search page first to establish session/cookies
        await self._client.get(self._base_url)

        # POST the search form with date range and showall
        form_data = {
            "receivedFrom": date_from.strftime(DATE_FORMAT_REQUEST),
            "receivedTo": date_to.strftime(DATE_FORMAT_REQUEST),
            "showall": "showall",
        }
        response = await self._client.post(self._base_url, data=form_data)
        response.raise_for_status()

        return self._parse_results(response.text, str(response.url))

    def _parse_results(self, html: str, base_url: str) -> List[ApplicationSummary]:
        """Extract application UIDs and URLs from the results table.

        Ocella2 results have two tables: the first is layout chrome,
        the second contains actual results with a header row then data rows.
        Each data row has a link in the first td cell containing the reference.
        """
        soup = BeautifulSoup(html, "lxml")
        results: List[ApplicationSummary] = []

        tables = soup.find_all("table")
        if len(tables) < 2:
            # Fallback: try any table with application links
            for table in tables:
                results.extend(self._extract_from_table(table, base_url))
            if not results:
                # Last resort: find any links to planningDetails
                results = self._extract_detail_links(soup, base_url)
            return results

        # The second table typically holds search results
        results_table = tables[1]
        results = self._extract_from_table(results_table, base_url)

        if not results:
            # Try all tables as fallback
            for table in tables[2:]:
                results.extend(self._extract_from_table(table, base_url))

        if not results:
            results = self._extract_detail_links(soup, base_url)

        return results

    def _extract_from_table(self, table, base_url: str) -> List[ApplicationSummary]:
        """Extract application summaries from a result table."""
        results = []
        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header row
            link = row.find("a", href=True)
            if not link:
                continue
            uid = link.get_text(strip=True)
            if not uid:
                continue
            href = link["href"]
            abs_url = urljoin(base_url, href)
            results.append(ApplicationSummary(uid=uid, url=abs_url))
        return results

    def _extract_detail_links(self, soup: BeautifulSoup, base_url: str) -> List[ApplicationSummary]:
        """Fallback: extract any links pointing to planningDetails."""
        results = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if DETAIL_PATH in href or "reference=" in href:
                uid = link.get_text(strip=True)
                if uid:
                    abs_url = urljoin(base_url, href)
                    results.append(ApplicationSummary(uid=uid, url=abs_url))
        return results

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        url = application.url
        if not url:
            url = self._detail_url(application.uid)

        html = await self._client.get_html(url)
        return self._parse_detail(html, url, application.uid)

    def _detail_url(self, uid: str) -> str:
        """Build detail page URL from a reference number."""
        base = self._base_url.rsplit("/", 1)[0]
        return f"{base}/{DETAIL_PATH}?from=planningSearch&reference={quote_plus(uid)}"

    def _parse_detail(self, html: str, url: str, uid: str) -> ApplicationDetail:
        """Parse the detail page for a single application.

        Ocella2 detail pages use a table with td pairs:
        <td>Label</td><td>Value</td>
        """
        soup = BeautifulSoup(html, "lxml")

        reference = _extract_detail_field(soup, "Reference") or uid
        description = _extract_detail_field(soup, "Proposal") or ""
        address = _extract_detail_field(soup, "Location") or ""
        date_received_str = _extract_detail_field(soup, "Received") or ""
        date_validated_str = _extract_detail_field(soup, "Validated") or ""
        status = _extract_detail_field(soup, "Status")
        ward = _extract_detail_field(soup, "Ward")
        parish = _extract_detail_field(soup, "Parish")
        applicant = _extract_detail_field(soup, "Applicant")
        case_officer = _extract_detail_field(soup, "Officer")
        decision = _extract_detail_field(soup, "Decision")
        decision_date_str = _extract_detail_field(soup, "Decided") or ""
        target_date_str = _extract_detail_field(soup, "Decision By") or ""
        consultation_end_str = _extract_detail_field(soup, "Comment By") or ""
        application_type = _extract_detail_field(soup, "Type")
        agent = _extract_detail_field(soup, "Agent")

        # Build raw_data with all non-None fields
        raw = {}
        if decision:
            raw["decision"] = decision
        if _extract_detail_field(soup, "Decided"):
            raw["decision_date"] = decision_date_str
        if target_date_str:
            raw["target_decision_date"] = target_date_str
        if consultation_end_str:
            raw["consultation_end_date"] = consultation_end_str
        if agent:
            raw["agent"] = agent

        # Look for comment form URL
        comment_form = soup.find("form", {"name": "comment"})
        if comment_form and comment_form.get("action"):
            raw["comment_url"] = urljoin(url, comment_form["action"])

        return ApplicationDetail(
            reference=reference,
            address=address,
            description=description,
            url=url,
            application_type=application_type,
            status=status,
            decision=decision,
            date_received=_parse_date(date_received_str),
            date_validated=_parse_date(date_validated_str),
            ward=ward,
            parish=parish,
            applicant_name=applicant,
            case_officer=case_officer,
            raw_data=raw,
        )

    async def fetch_detail_by_uid(self, uid: str) -> Optional[ApplicationDetail]:
        """Fetch details for a single application by reference number."""
        url = self._detail_url(uid)
        try:
            html = await self._client.get_html(url)
            return self._parse_detail(html, url, uid)
        except Exception:
            return None
