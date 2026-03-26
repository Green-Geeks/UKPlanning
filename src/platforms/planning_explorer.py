"""PlanningExplorer platform scraper (~20 councils including Birmingham, Liverpool, Camden)."""
from datetime import date
from urllib.parse import urljoin

from src.core.browser import HttpClient
from src.core.config import CouncilConfig
from src.core.parser import PageParser
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

PE_SEARCH_SELECTORS = {
    "result_links": "table.display_table td a",
    "result_uids": "table.display_table td a",
    "next_page": "a:has(img[title='Go to next page'])",
    "dates_link": "a:-soup-contains('Application Dates')",
}

PE_DETAIL_SELECTORS = {
    "reference": "li:has(span:-soup-contains('Application Number'))",
    "address": "li:has(span:-soup-contains('Site Address'))",
    "description": "li:has(span:-soup-contains('Proposal'))",
    "date_validated": "li:has(span:-soup-contains('Application Registered'))",
    "application_type": "li:has(span:-soup-contains('Application Type'))",
    "status": "li:has(span:-soup-contains('Status'))",
    "case_officer": "li:has(span:-soup-contains('Case Officer'))",
    "ward": "li:has(span:-soup-contains('Ward'))",
    "parish": "li:has(span:-soup-contains('Parish'))",
}

PE_DATES_SELECTORS = {
    "date_received": "li:has(span:-soup-contains('Received'))",
    "date_validated": "li:has(span:-soup-contains('Validated'))",
    "target_date": "li:has(span:-soup-contains('Target Date'))",
    "decision_date": "li:has(span:-soup-contains('Decision Date'))",
}


class PlanningExplorerScraper(BaseScraper):
    SEARCH_PATH = "/GeneralSearch.aspx"
    DATE_FORMAT = "%d/%m/%Y"
    DATE_FROM_FIELD = "dateStart"
    DATE_TO_FIELD = "dateEnd"

    def __init__(self, config):
        super().__init__(config)
        self._parser = PageParser()
        self._client = HttpClient(timeout=30, rate_limit_delay=config.rate_limit_delay)
        self._search_selectors = {**PE_SEARCH_SELECTORS}
        self._detail_selectors = {**PE_DETAIL_SELECTORS}
        self._dates_selectors = {**PE_DATES_SELECTORS}
        if config.selectors:
            for key, val in config.selectors.items():
                for sel_dict in (self._search_selectors, self._detail_selectors, self._dates_selectors):
                    if key in sel_dict:
                        sel_dict[key] = val

    async def gather_ids(self, date_from, date_to):
        search_url = self.config.base_url + self.SEARCH_PATH
        await self._client.get_html(search_url)
        form_data = {
            self.DATE_FROM_FIELD: date_from.strftime(self.DATE_FORMAT),
            self.DATE_TO_FIELD: date_to.strftime(self.DATE_FORMAT),
        }
        response = await self._client.post(search_url, data=form_data)
        html = response.text
        applications = []
        while True:
            page_apps = self._parse_results(html)
            applications.extend(page_apps)
            next_el = self._parser.select_one(html, self._search_selectors["next_page"])
            if next_el is None:
                break
            next_url = urljoin(self.config.base_url, next_el.get("href", ""))
            html = await self._client.get_html(next_url)
        return applications

    def _parse_results(self, html):
        links = self._parser.extract_list(html, self._search_selectors["result_links"], attr="href")
        uids = self._parser.extract_list(html, self._search_selectors["result_uids"])
        results = []
        for i, link in enumerate(links):
            uid = uids[i] if i < len(uids) else None
            if uid:
                results.append(ApplicationSummary(uid=uid, url=urljoin(self.config.base_url, link)))
        return results

    async def fetch_detail(self, application):
        detail_html = await self._client.get_html(application.url)
        detail_data = self._extract_li_fields(detail_html, self._detail_selectors)
        dates_data = {}
        dates_el = self._parser.select_one(detail_html, self._search_selectors["dates_link"])
        if dates_el:
            dates_url = urljoin(self.config.base_url, dates_el.get("href", ""))
            dates_html = await self._client.get_html(dates_url)
            dates_data = self._extract_li_fields(dates_html, self._dates_selectors)
        raw = {k: v for d in (detail_data, dates_data) for k, v in d.items() if v is not None}
        return ApplicationDetail(
            reference=detail_data.get("reference") or application.uid,
            address=detail_data.get("address") or "",
            description=detail_data.get("description") or "",
            url=application.url,
            application_type=detail_data.get("application_type"),
            status=detail_data.get("status"),
            date_received=self._parse_date(dates_data.get("date_received")),
            date_validated=self._parse_date(detail_data.get("date_validated")),
            ward=detail_data.get("ward"),
            parish=detail_data.get("parish"),
            case_officer=detail_data.get("case_officer"),
            raw_data=raw,
        )

    def _extract_li_fields(self, html, selectors):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        result = {}
        for field_name, selector in selectors.items():
            el = soup.select_one(selector)
            if el:
                span = el.find("span")
                if span:
                    span.decompose()
                result[field_name] = el.get_text(strip=True)
            else:
                result[field_name] = None
        return result

    @staticmethod
    def _parse_date(date_str):
        if not date_str:
            return None
        from dateutil import parser as dateutil_parser
        try:
            return dateutil_parser.parse(date_str, dayfirst=True).date()
        except (ValueError, TypeError):
            return None
