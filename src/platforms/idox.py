"""Idox platform scraper for UK planning authorities.

Idox is the dominant planning portal platform, used by ~250 UK councils.
This module defines the default selectors and the scraper class.
"""

from datetime import date
from urllib.parse import urljoin

from src.core.browser import HttpClient
from src.core.config import CouncilConfig
from src.core.parser import PageParser
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper, ScrapeResult

IDOX_SEARCH_SELECTORS = {
    "result_links": "ul#searchresults li.searchresult > a",
    "result_uids": "ul#searchresults li.searchresult p.metainfo > span:first-child",
    "next_page": "a.next",
    "dates_tab": "a#subtab_dates",
    "info_tab": "a#subtab_details",
}

IDOX_SELECTORS = {
    "reference": "th:-soup-contains('Reference') + td",
    "address": "th:-soup-contains('Address') + td",
    "description": "th:-soup-contains('Proposal') + td",
    "status": "th:-soup-contains('Status') + td",
    "alt_reference": "th:-soup-contains('Alternative Reference') + td",
}

IDOX_DATES_SELECTORS = {
    "date_received": "th:-soup-contains('Application Received') + td",
    "date_validated": "th:-soup-contains('Validated') + td",
    "expiry_date": "th:-soup-contains('Expiry Date') + td",
    "target_date": "th:-soup-contains('Target Date') + td",
    "decision_date": "th:-soup-contains('Decision Made Date') + td",
    "consultation_expiry": "th:-soup-contains('Standard Consultation Expiry') + td",
}

IDOX_INFO_SELECTORS = {
    "application_type": "th:-soup-contains('Application Type') + td",
    "case_officer": "th:-soup-contains('Case Officer') + td",
    "parish": "th:-soup-contains('Parish') + td",
    "ward": "th:-soup-contains('Ward') + td",
    "applicant_name": "th:-soup-contains('Applicant Name') + td",
    "agent_name": "th:-soup-contains('Agent Name') + td",
    "decision_level": "th:-soup-contains('Decision Level') + td",
}


class IdoxScraper(BaseScraper):
    """Scraper for Idox-based planning portals (~250 UK councils)."""

    SEARCH_PATH = "/search.do?action=advanced"
    RESULTS_PATH = "/advancedSearchResults.do?action=firstPage"
    DATE_FORMAT = "%d/%m/%Y"

    DATE_FROM_FIELD = "date(applicationReceivedStart)"
    DATE_TO_FIELD = "date(applicationReceivedEnd)"
    SEARCH_TYPE_FIELD = "searchType"
    SEARCH_TYPE_VALUE = "Application"

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._parser = PageParser()
        self._client = HttpClient(
            timeout=30,
            rate_limit_delay=config.rate_limit_delay,
        )
        self._search_selectors = {**IDOX_SEARCH_SELECTORS}
        self._summary_selectors = {**IDOX_SELECTORS}
        self._dates_selectors = {**IDOX_DATES_SELECTORS}
        self._info_selectors = {**IDOX_INFO_SELECTORS}
        if config.selectors:
            for key, val in config.selectors.items():
                for sel_dict in (self._search_selectors, self._summary_selectors,
                                 self._dates_selectors, self._info_selectors):
                    if key in sel_dict:
                        sel_dict[key] = val

    async def gather_ids(self, date_from: date, date_to: date) -> list[ApplicationSummary]:
        """Search Idox portal for applications in date range, handling pagination."""
        search_url = self.config.base_url + self.SEARCH_PATH
        await self._client.get_html(search_url)

        results_url = self.config.base_url + self.RESULTS_PATH
        form_data = {
            self.DATE_FROM_FIELD: date_from.strftime(self.DATE_FORMAT),
            self.DATE_TO_FIELD: date_to.strftime(self.DATE_FORMAT),
            self.SEARCH_TYPE_FIELD: self.SEARCH_TYPE_VALUE,
        }
        response = await self._client.post(results_url, data=form_data)
        html = response.text

        applications = []
        while True:
            page_apps = self._parse_search_results(html)
            applications.extend(page_apps)

            next_el = self._parser.select_one(html, self._search_selectors["next_page"])
            if next_el is None:
                break
            next_url = urljoin(self.config.base_url, next_el["href"])
            html = await self._client.get_html(next_url)

        return applications

    def _parse_search_results(self, html: str) -> list[ApplicationSummary]:
        """Extract application summaries from a single results page."""
        links = self._parser.extract_list(html, self._search_selectors["result_links"], attr="href")
        uids = self._parser.extract_list(html, self._search_selectors["result_uids"])

        results = []
        for i, link in enumerate(links):
            uid = uids[i] if i < len(uids) else None
            if uid:
                abs_url = urljoin(self.config.base_url, link)
                results.append(ApplicationSummary(uid=uid, url=abs_url))
        return results

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        """Fetch full details — stub, implemented in next task."""
        raise NotImplementedError("fetch_detail not yet implemented")
