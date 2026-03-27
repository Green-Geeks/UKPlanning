"""Telford & Wrekin Council planning scraper.

Custom ASP.NET application at secure.telford.gov.uk/planningsearch.
Single-phase POST: GET page for ViewState, POST with dates to default.aspx,
parse results table, paginate via __doPostBack, fetch detail pages.
"""
import re
from datetime import date, datetime
from typing import Dict, List, Optional
import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

BASE_URL = "https://secure.telford.gov.uk/planningsearch"
DETAIL_BASE = "https://secure.telford.gov.uk/planning"


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d-%m-%y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _extract_hidden_fields(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    fields = {}
    for inp in soup.find_all("input", type="hidden"):
        name = inp.get("name", "")
        if name:
            fields[name] = inp.get("value", "")
    return fields


def _extract_results(html: str) -> List[ApplicationSummary]:
    """Parse application references and URLs from the results table."""
    summaries = []
    seen = set()
    for match in re.finditer(
        r'href="(https://secure\.telford\.gov\.uk/planning/'
        r'pa-applicationsummary\.aspx\?applicationnumber=([^"]+))"',
        html,
    ):
        url = match.group(1)
        ref = match.group(2).replace("%2f", "/").replace("%2F", "/")
        if ref not in seen:
            seen.add(ref)
            summaries.append(ApplicationSummary(uid=ref, url=url))
    return summaries


class TelfordScraper(BaseScraper):
    """Scraper for Telford & Wrekin's custom ASP.NET planning portal."""

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=True,
            timeout=30,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        search_url = f"{BASE_URL}/"

        # GET search page to establish session and get ViewState
        resp = await self._client.get(search_url)
        resp.raise_for_status()
        fields = _extract_hidden_fields(resp.text)

        # POST with date range to default.aspx
        post_data = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": fields.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR": fields.get("__VIEWSTATEGENERATOR", ""),
            "__PREVIOUSPAGE": fields.get("__PREVIOUSPAGE", ""),
            "__EVENTVALIDATION": fields.get("__EVENTVALIDATION", ""),
            "ctl00$ContentPlaceHolder1$txtPlanningKeywords": "",
            "ctl00$ContentPlaceHolder1$dlPlanningParishs": "0",
            "ctl00$ContentPlaceHolder1$dlPlanningWard": "0",
            "ctl00$ContentPlaceHolder1$ddlPlanningapplicationtype": "0",
            "ctl00$ContentPlaceHolder1$DCdatefrom": date_from.strftime("%d-%m-%Y"),
            "ctl00$ContentPlaceHolder1$DCdateto": date_to.strftime("%d-%m-%Y"),
            "ctl00$ContentPlaceHolder1$txtDCAgent": "",
            "ctl00$ContentPlaceHolder1$txtDCApplicant": "",
            "ctl00$ContentPlaceHolder1$btnSearchPlanningDetails": "Search",
        }

        resp = await self._client.post(
            f"{BASE_URL}/default.aspx",
            data=post_data,
            headers={"Referer": search_url},
        )
        resp.raise_for_status()

        # Parse first page of results
        all_summaries = _extract_results(resp.text)

        # Paginate through remaining pages
        page_html = resp.text
        while True:
            next_target = self._find_next_page_target(page_html)
            if not next_target:
                break

            page_fields = _extract_hidden_fields(page_html)
            page_data = {
                "__EVENTTARGET": next_target,
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": page_fields.get("__VIEWSTATE", ""),
                "__VIEWSTATEGENERATOR": page_fields.get("__VIEWSTATEGENERATOR", ""),
                "__EVENTVALIDATION": page_fields.get("__EVENTVALIDATION", ""),
            }

            resp = await self._client.post(
                f"{BASE_URL}/default.aspx",
                data=page_data,
                headers={"Referer": f"{BASE_URL}/default.aspx"},
            )
            resp.raise_for_status()
            page_html = resp.text

            new_summaries = _extract_results(page_html)
            if not new_summaries:
                break
            all_summaries.extend(new_summaries)

        return all_summaries

    @staticmethod
    def _find_next_page_target(html: str) -> Optional[str]:
        """Find the __doPostBack target for the next page button."""
        match = re.search(
            r"__doPostBack\('(ctl00\$ContentPlaceHolder1\$gvResults\$ctl\d+\$lbPagerTopNext)',''\)",
            html,
        )
        if not match:
            return None

        # Only return if "Next" link is actually active (not on last page)
        target = match.group(1)
        # Check the link isn't disabled
        context_start = max(0, match.start() - 200)
        context = html[context_start : match.end() + 50]
        if "disabled" in context.lower():
            return None
        return target

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        resp = await self._client.get(application.url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        data = {}
        for row in soup.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if th and td:
                label = th.get_text(strip=True).lower()
                value = td.get_text(separator=" ", strip=True)
                data[label] = value

        return ApplicationDetail(
            reference=application.uid,
            address=data.get("site address", ""),
            description=data.get("description of proposal", ""),
            url=application.url,
            application_type=data.get("application type"),
            status=data.get("decision"),
            date_received=_parse_date(data.get("date valid", "")),
            ward=data.get("ward"),
            parish=data.get("parish"),
            applicant_name=data.get("applicant"),
            case_officer=data.get("case officer"),
            raw_data=data,
        )
