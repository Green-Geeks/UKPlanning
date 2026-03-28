"""Dorset Council planning scraper.

Custom ASP.NET site at planning.dorsetcouncil.gov.uk with Telerik RadDatePicker
and disclaimer acceptance. Uses advanced search for date-range queries.
"""
import re
from datetime import date
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.core.browser import HttpClient
from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

BASE_URL = "https://planning.dorsetcouncil.gov.uk"


class DorsetScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._client = HttpClient(timeout=60, rate_limit_delay=config.rate_limit_delay)
        self._disclaimer_accepted = False

    async def _accept_disclaimer(self):
        if self._disclaimer_accepted:
            return
        r = await self._client.get(BASE_URL + "/")
        soup = BeautifulSoup(r.text, "lxml")
        form = soup.find("form")
        if not form:
            return
        fields = {}
        for inp in form.find_all("input"):
            name = inp.get("name", "")
            if name:
                fields[name] = inp.get("value", "")
        action = form.get("action", "")
        await self._client.post(urljoin(str(r.url), action), data=fields)
        self._disclaimer_accepted = True

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        await self._accept_disclaimer()

        r = await self._client.get(BASE_URL + "/advsearch.aspx")
        soup = BeautifulSoup(r.text, "lxml")
        form = soup.find("form")
        form_data = {}
        for inp in form.find_all("input"):
            name = inp.get("name", "")
            if name:
                form_data[name] = inp.get("value", "")

        form_data["ctl00$ContentPlaceHolder1$txtDateReceivedFrom$dateInput"] = date_from.strftime("%d/%m/%Y")
        form_data["ctl00$ContentPlaceHolder1$txtDateReceivedTo$dateInput"] = date_to.strftime("%d/%m/%Y")
        form_data["ctl00$ContentPlaceHolder1$txtDateReceivedFrom"] = date_from.isoformat()
        form_data["ctl00$ContentPlaceHolder1$txtDateReceivedTo"] = date_to.isoformat()
        form_data["ctl00$ContentPlaceHolder1$btnSearch3"] = "Search"

        for key in list(form_data.keys()):
            if ("btnSearch" in key and key != "ctl00$ContentPlaceHolder1$btnSearch3") or "btnReset" in key:
                del form_data[key]

        r2 = await self._client.post(BASE_URL + "/advsearch.aspx", data=form_data)
        soup2 = BeautifulSoup(r2.text, "lxml")

        results = []
        for i in range(100):
            link_el = soup2.find(id=f"ctl00_ContentPlaceHolder1_lvResults_ctrl{i}_hypDisplayRecord")
            if not link_el:
                break
            ref = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            url = urljoin(BASE_URL + "/", href)
            results.append(ApplicationSummary(uid=ref, url=url))

        # TODO: pagination via RadDataPager if needed (>10 results per page)
        return results

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        await self._accept_disclaimer()

        html = await self._client.get_html(application.url)
        soup = BeautifulSoup(html, "lxml")

        details_panel = soup.find(id="ctl00_ContentPlaceHolder1_pvDetails")
        detail_text = details_panel.get_text(" ", strip=True) if details_panel else ""

        reference = self._extract_field(detail_text, r"Application No\s*(.+?)(?:Case Officer|$)")
        case_officer = self._extract_field(detail_text, r"Case Officer\s*(.+?)(?:Status|$)")
        status = self._extract_field(detail_text, r"Status\s*(.+?)(?:Application Type|$)")
        app_type = self._extract_field(detail_text, r"Application Type\s*(.+?)(?:Proposal|$)")
        description = self._extract_field(detail_text, r"Proposal\s*(.+?)(?:Date Received|$)")
        date_received_str = self._extract_field(detail_text, r"Date Received\s*(.+?)(?:Target|Consultation|$)")
        ward = self._extract_field(detail_text, r"Ward\s*(.+?)(?:Parish|$)")
        parish = self._extract_field(detail_text, r"Parish\s*(.+?)(?:Applicant|Agent|$)")

        location_panel = soup.find(id="ctl00_ContentPlaceHolder1_pvLocation")
        address = ""
        if location_panel:
            loc_text = location_panel.get_text(" ", strip=True)
            address = self._extract_field(loc_text, r"Address\s*(.+?)(?:Easting|$)")

        applicant_panel = soup.find(id="ctl00_ContentPlaceHolder1_divApplicantDetails")
        applicant = ""
        if applicant_panel:
            app_text = applicant_panel.get_text(" ", strip=True)
            applicant = self._extract_field(app_text, r"Applicant\s*(.+?)(?:Applicant's Address|$)")

        return ApplicationDetail(
            reference=reference or application.uid,
            address=address,
            description=description or "",
            url=application.url,
            application_type=app_type,
            status=status,
            date_received=self._parse_date(date_received_str),
            ward=ward,
            parish=parish,
            applicant_name=applicant,
            case_officer=case_officer,
            raw_data={"detail_text": detail_text[:500]},
        )

    @staticmethod
    def _extract_field(text: str, pattern: str) -> str:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
        return ""

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[date]:
        if not date_str:
            return None
        from dateutil import parser as dateutil_parser
        try:
            return dateutil_parser.parse(date_str, dayfirst=True).date()
        except (ValueError, TypeError):
            return None
