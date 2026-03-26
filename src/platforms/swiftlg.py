"""SwiftLG platform scraper (~21 councils). Multiple HTML layout variants."""
from datetime import date
from urllib.parse import urljoin

from src.core.browser import HttpClient
from src.core.config import CouncilConfig
from src.core.parser import PageParser
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

SWIFTLG_SEARCH_SELECTORS = {
    "result_links": "form table td a",
    "result_uids": "form table td a",
    "next_page": "form a[href*='StartIndex']",
}

SWIFTLG_SPAN_SELECTORS = {
    "reference": "span:-soup-contains('Application Ref') + p",
    "date_validated": "span:-soup-contains('Registration Date') + p",
    "address": "span:-soup-contains('Main Location') + p",
    "description": "span:-soup-contains('Full Description') + p",
    "application_type": "span:-soup-contains('Application Type') + p",
    "date_received": "span:-soup-contains('Application Date') + p",
    "decision": "span:-soup-contains('Decision') + p",
    "case_officer": "span:-soup-contains('Case Officer') + p",
}

SWIFTLG_LABEL_SELECTORS = {
    "reference": "label:-soup-contains('Reference') + p",
    "date_validated": "label:-soup-contains('Registration Date') + p",
    "address": "label:-soup-contains('Main Location') + p",
    "description": "label:-soup-contains('Full Description') + p",
    "application_type": "label:-soup-contains('Application Type') + p",
    "date_received": "label:-soup-contains('Application Date') + p",
    "decision": "label:-soup-contains('Decision') + p",
    "case_officer": "label:-soup-contains('Case Officer') + p",
}


class SwiftLGScraper(BaseScraper):
    SEARCH_PATH = "/wphappcriteria.display"
    DATE_FORMAT = "%d/%m/%Y"
    DATE_FROM_FIELD = "REGFROMDATE.MAINBODY.WPACIS.1"
    DATE_TO_FIELD = "REGTODATE.MAINBODY.WPACIS.1"

    def __init__(self, config, detail_selectors=None):
        super().__init__(config)
        self._parser = PageParser()
        self._client = HttpClient(timeout=30, rate_limit_delay=config.rate_limit_delay)
        self._search_selectors = {**SWIFTLG_SEARCH_SELECTORS}
        self._detail_selectors = detail_selectors or {**SWIFTLG_SPAN_SELECTORS}
        if config.selectors:
            for key, val in config.selectors.items():
                for sel_dict in (self._search_selectors, self._detail_selectors):
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
        html = await self._client.get_html(application.url)
        data = self._parser.extract(html, self._detail_selectors)
        raw = {k: v for k, v in data.items() if v is not None}
        return ApplicationDetail(
            reference=data.get("reference") or application.uid,
            address=data.get("address") or "",
            description=data.get("description") or "",
            url=application.url,
            application_type=data.get("application_type"),
            status=data.get("decision"),
            date_received=self._parse_date(data.get("date_received")),
            date_validated=self._parse_date(data.get("date_validated")),
            case_officer=data.get("case_officer"),
            raw_data=raw,
        )

    @staticmethod
    def _parse_date(date_str):
        if not date_str:
            return None
        from dateutil import parser as dateutil_parser
        try:
            return dateutil_parser.parse(date_str, dayfirst=True).date()
        except (ValueError, TypeError):
            return None


class SwiftLGLabelScraper(SwiftLGScraper):
    """Variant using <label> tags instead of <span> tags."""
    def __init__(self, config):
        super().__init__(config, detail_selectors={**SWIFTLG_LABEL_SELECTORS})
