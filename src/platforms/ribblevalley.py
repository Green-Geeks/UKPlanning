"""Ribble Valley Borough Council planning scraper.

Custom Jadu CMS portal at webportal.ribblevalley.gov.uk.
GET-based search with day/month/year date parameters, paginated via lowerLimit.
Detail pages at /planningApplication/{numeric_id} with labeled div structure.
"""
import re
from datetime import date, datetime
from typing import List, Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

BASE_URL = "https://webportal.ribblevalley.gov.uk"
SEARCH_URL = f"{BASE_URL}/planningApplication/search/results"
DETAIL_URL = f"{BASE_URL}/planningApplication"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
}

UID_RE = re.compile(r"/planningApplication/(\d+)\s*$")
PAGE_SIZE = 10


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ["%d/%m/%Y", "%d %b %Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


class RibbleValleyScraper(BaseScraper):
    """Scraper for Ribble Valley's Jadu planning portal."""

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=30,
        )

    def _build_search_params(self, date_from: date, date_to: date, offset: int = 0) -> dict:
        return {
            "location": "",
            "applicant": "",
            "developmentDescription": "",
            "decisionType": "",
            "decisionDate": "",
            "fromDay": str(date_from.day),
            "fromMonth": str(date_from.month),
            "fromYear": str(date_from.year),
            "toDay": str(date_to.day),
            "toMonth": str(date_to.month),
            "toYear": str(date_to.year),
            "advancedSearch": "Search",
            "lowerLimit": str(offset),
        }

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        summaries = []
        seen = set()
        offset = 0
        max_pages = 100

        for _ in range(max_pages):
            params = self._build_search_params(date_from, date_to, offset)
            resp = await self._client.get(SEARCH_URL, params=params)
            resp.raise_for_status()

            # Check for no results redirect
            if "/no_results" in str(resp.url):
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract total count from heading like "71 results for"
            if offset == 0:
                h2 = soup.find("h2")
                if h2:
                    count_match = re.search(r"(\d+)\s+results?\s+for", h2.get_text())
                    if count_match:
                        total = int(count_match.group(1))

            # Parse result rows - links to /planningApplication/{id}
            new_items = []
            for link in soup.find_all("a", href=re.compile(r"/planningApplication/\d+")):
                href = link.get("href", "")
                uid_match = UID_RE.search(href)
                if not uid_match:
                    continue

                numeric_id = uid_match.group(1)
                if numeric_id in seen:
                    continue
                seen.add(numeric_id)

                ref = link.get_text(strip=True)
                url = f"{BASE_URL}{href}" if href.startswith("/") else href

                new_items.append(ApplicationSummary(uid=numeric_id, url=url))

            if not new_items:
                break

            summaries.extend(new_items)
            offset += PAGE_SIZE

            # Single result redirects directly to detail page
            if len(summaries) == 1 and not new_items:
                single_match = UID_RE.search(str(resp.url))
                if single_match:
                    numeric_id = single_match.group(1)
                    if numeric_id not in seen:
                        summaries.append(ApplicationSummary(
                            uid=numeric_id,
                            url=str(resp.url),
                        ))
                break

        return summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        url = application.url or f"{DETAIL_URL}/{application.uid}"

        resp = await self._client.get(url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text("\n", strip=True)

        # Reference from heading: "Application 3/2026/0208"
        reference = application.uid
        h2 = soup.find("h2")
        if h2:
            ref_match = re.search(r"Application\s+(\S+)", h2.get_text())
            if ref_match:
                reference = ref_match.group(1)

        # Application type - bold text before description
        application_type = None
        for strong in soup.find_all("strong"):
            t = strong.get_text(strip=True)
            if re.match(r"(?:Full|Outline|Householder|Listed|Discharge|Reserved|Application|Certificate|Lawful|Prior|Advertisement|Tree|Variation|Removal|Retention|Change)", t, re.I):
                application_type = t
                break

        # Description - paragraph after application type
        description = ""
        desc_p = soup.find("p", class_="first")
        if desc_p:
            description = desc_p.get_text(strip=True)
            # Strip leading application type if present
            if application_type and description.startswith(application_type):
                description = description[len(application_type):].strip()

        # Extract labeled fields from the page text
        def extract_field(label: str) -> str:
            pattern = rf"{re.escape(label)}\s*(.+?)(?:\n|$)"
            m = re.search(pattern, text)
            return m.group(1).strip() if m else ""

        def extract_between(start: str, end: str) -> str:
            pattern = rf"{re.escape(start)}\s*(.+?)\s*(?:{re.escape(end)}|$)"
            m = re.search(pattern, text, re.S)
            return m.group(1).strip() if m else ""

        # Address - from "Development address" section
        address = ""
        addr_match = re.search(r"Development address\s*(.+?)(?=Ward|Parish|Applicant|Agent|Officer|Key dates|Planning Status|$)", text, re.S)
        if addr_match:
            address = re.sub(r"\s+", " ", addr_match.group(1)).strip()

        # Ward and Parish
        ward = ""
        ward_match = re.search(r"Ward\s*:\s*(.+?)(?:\n|$)", text)
        if ward_match:
            ward = ward_match.group(1).strip()

        parish = ""
        parish_match = re.search(r"Parish\s*:\s*(.+?)(?:\n|$)", text)
        if parish_match:
            parish = parish_match.group(1).strip()

        # Key dates
        date_received = None
        recv_match = re.search(r"Received\s*:?\s*(\d{2}/\d{2}/\d{4})", text)
        if recv_match:
            date_received = _parse_date(recv_match.group(1))

        date_validated = None
        valid_match = re.search(r"Valid\s*:?\s*(\d{2}/\d{2}/\d{4})", text)
        if valid_match:
            date_validated = _parse_date(valid_match.group(1))

        meeting_date = None
        committee_match = re.search(r"Committee\s*:?\s*(\d{2}/\d{2}/\d{4})", text)
        if committee_match:
            meeting_date = committee_match.group(1)

        # Officer
        case_officer = ""
        officer_match = re.search(r"Officer\s*(.+?)(?:Tel:|Email:|Applicant|Agent|Key|Planning|Decision|\n\n)", text, re.S)
        if officer_match:
            case_officer = officer_match.group(1).strip().split("\n")[0].strip()

        # Applicant
        applicant_name = ""
        app_match = re.search(r"Applicant\s*(.+?)(?:Agent|Officer|Key|Planning|Decision|\n\n)", text, re.S)
        if app_match:
            applicant_name = app_match.group(1).strip().split("\n")[0].strip()
            # Remove trailing address parts
            applicant_name = re.sub(r",\s*\d.*$", "", applicant_name).strip()

        # Agent
        agent_name = ""
        agent_match = re.search(r"Agent\s*(.+?)(?:Officer|Applicant|Key|Planning|Decision|\n\n)", text, re.S)
        if agent_match:
            agent_name = agent_match.group(1).strip().split("\n")[0].strip()
            agent_name = re.sub(r",\s*\d.*$", "", agent_name).strip()

        # Status
        status = ""
        status_match = re.search(r"Planning Status\s*(.+?)(?:Decision|Attached|Comment|\n\n|$)", text, re.S)
        if status_match:
            status = status_match.group(1).strip().split("\n")[0].strip()

        # Decision
        decision = ""
        decision_date = None
        dec_match = re.search(r"Decision\s*(.+?)(?:Date\s*:\s*(\d{2}/\d{2}/\d{4}))?(?:Attached|Comment|\n\n|$)", text, re.S)
        if dec_match:
            decision = dec_match.group(1).strip().split("\n")[0].strip()
            if dec_match.group(2):
                decision_date = dec_match.group(2)

        return ApplicationDetail(
            reference=reference,
            address=address,
            description=description,
            url=url,
            application_type=application_type,
            status=status or None,
            decision=decision or None,
            date_received=date_received,
            date_validated=date_validated,
            ward=ward or None,
            parish=parish or None,
            applicant_name=applicant_name or None,
            case_officer=case_officer or None,
            raw_data={
                "numeric_id": application.uid,
                "agent_name": agent_name or None,
                "meeting_date": meeting_date,
                "decision_date": decision_date,
            },
        )
