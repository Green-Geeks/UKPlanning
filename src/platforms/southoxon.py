"""South Oxfordshire and Vale of White Horse (CCM) planning scraper.

JSP/CCM platform used by both South Oxfordshire (data.southoxon.gov.uk)
and Vale of White Horse (data.whitehorsedc.gov.uk). Search via GET with
date components (SDAY/SMONTH/SYEAR, EDAY/EMONTH/EYEAR) and MODULE params.
Detail pages via MODULE=ApplicationDetails&REF={uid}.
"""
import re
from datetime import date, datetime
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urlencode, urljoin

import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

# CCM platform endpoints per council
CCM_CONFIGS = {
    "southoxfordshire": {
        "base": "https://data.southoxon.gov.uk/ccm/support/Main.jsp",
        "search_page": "https://data.southoxon.gov.uk/ccm/planning/ApplicationCriteria.jsp",
    },
    "whitehorse": {
        "base": "https://data.whitehorsedc.gov.uk/java/support/Main.jsp",
        "search_page": "https://data.whitehorsedc.gov.uk/java/support/Main.jsp?MODULE=ApplicationCriteria&TYPE=Application",
    },
}


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    s = s.strip()
    for fmt in ["%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


class SouthOxonScraper(BaseScraper):
    """Scraper for CCM/JSP planning portals (South Oxon + Vale of White Horse)."""

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        ccm = CCM_CONFIGS.get(config.authority_code, CCM_CONFIGS["southoxfordshire"])
        self._base_url = ccm["base"]
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=True,
            timeout=30,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        params = {
            "MODULE": "ApplicationCriteriaList",
            "TYPE": "Application",
            "PARISH": "ALL",
            "AREA": "A",
            "APPTYPE": "ALL",
            "SDAY": f"{date_from.day:02d}",
            "SMONTH": f"{date_from.month:02d}",
            "SYEAR": str(date_from.year),
            "EDAY": f"{date_to.day:02d}",
            "EMONTH": f"{date_to.month:02d}",
            "EYEAR": str(date_to.year),
            "Submit": "Search",
        }

        url = f"{self._base_url}?{urlencode(params)}"
        resp = await self._client.get(url)
        resp.raise_for_status()

        return self._parse_results(resp.text, resp.url)

    def _parse_results(self, html: str, base_url) -> List[ApplicationSummary]:
        """Extract application references and URLs from the results page."""
        soup = BeautifulSoup(html, "html.parser")
        summaries = []

        # CCM lists applications as links in rowdiv containers
        # Pattern: <a href="Main.jsp?MODULE=ApplicationDetails&REF=P24/S1234/FUL">P24/S1234/FUL</a>
        for link in soup.find_all("a", href=re.compile(r"MODULE=ApplicationDetails")):
            href = link.get("href", "")
            uid = link.get_text(strip=True)
            if not uid:
                continue

            detail_url = urljoin(str(base_url), href)
            summaries.append(ApplicationSummary(uid=uid, url=detail_url))

        return summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        url = application.url
        if not url:
            url = f"{self._base_url}?MODULE=ApplicationDetails&REF={quote_plus(application.uid)}"

        resp = await self._client.get(url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        fields = self._extract_fields(soup)

        # Grid reference parsing
        raw = {}
        grid_ref = fields.get("Grid Reference", "")
        grid_match = re.match(r"(\d+)\s*/\s*(\d+)", grid_ref)
        if grid_match:
            raw["easting"] = grid_match.group(1)
            raw["northing"] = grid_match.group(2)

        if fields.get("Appeal"):
            raw["appeal_status"] = fields["Appeal"]
        if fields.get("Start Consultation Period"):
            raw["consultation_start_date"] = fields["Start Consultation Period"]
        if fields.get("End Consultation Period"):
            raw["consultation_end_date"] = fields["End Consultation Period"]
        if fields.get("Target Decision Date"):
            raw["target_decision_date"] = fields["Target Decision Date"]

        return ApplicationDetail(
            reference=fields.get("reference", application.uid),
            address=_clean_text(fields.get("Location", "")),
            description=_clean_text(fields.get("Description", "")),
            url=url,
            application_type=fields.get("Application Type"),
            decision=fields.get("Decision"),
            date_received=_parse_date(fields.get("Date Received")),
            date_validated=_parse_date(fields.get("Registration Date")),
            applicant_name=_clean_text(fields.get("Applicant", "")),
            case_officer=_clean_text(fields.get("Case Officer", "")),
            raw_data=raw,
        )

    def _extract_fields(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract label/value pairs from CCM detail page.

        CCM uses div-based layout:
          <div class="tableheader">REF_NUMBER<img/></div>
          <div class="leftcelldiv">Label</div><div>Value</div>
          <div class="listrowdiv">Label Value</div>
        """
        fields: Dict[str, str] = {}

        # Reference from tableheader
        header = soup.find("div", class_="tableheader")
        if header:
            ref_text = header.get_text(strip=True)
            fields["reference"] = ref_text

        # Label/value pairs from leftcelldiv + next sibling div
        for label_div in soup.find_all("div", class_="leftcelldiv"):
            label = label_div.get_text(strip=True)
            value_div = label_div.find_next_sibling("div")
            if value_div and label:
                # Check for <pre> content (used for agent/applicant)
                pre = value_div.find("pre")
                value = pre.get_text(strip=True) if pre else value_div.get_text(strip=True)
                fields[label] = value

        # Date fields from listrowdiv
        for row_div in soup.find_all("div", class_="listrowdiv"):
            text = row_div.get_text(strip=True)
            for date_label in [
                "Date Received",
                "Registration Date",
                "Start Consultation Period",
                "End Consultation Period",
                "Target Decision Date",
            ]:
                if text.startswith(date_label):
                    date_val = text[len(date_label):].strip()
                    fields[date_label] = date_val

        return fields
