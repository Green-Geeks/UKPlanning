import pytest
from pathlib import Path
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from src.platforms.planning_explorer import (
    PlanningExplorerScraper, PE_SEARCH_SELECTORS, PE_DETAIL_SELECTORS, PE_DATES_SELECTORS,
)
from src.core.config import CouncilConfig
from src.core.parser import PageParser
from src.core.scraper import ApplicationSummary

FIXTURES = Path(__file__).parent / "fixtures"
PE_CONFIG = CouncilConfig(
    name="Birmingham", authority_code="birmingham", platform="planning_explorer",
    base_url="https://eplanning.birmingham.gov.uk/Northgate/PlanningExplorer",
)


class TestPESelectors:
    def setup_method(self):
        self.parser = PageParser()

    def test_search_results_links(self):
        html = (FIXTURES / "pe_search_results.html").read_text()
        links = self.parser.extract_list(html, PE_SEARCH_SELECTORS["result_links"], attr="href")
        assert len(links) == 2
        assert "12345" in links[0]

    def test_search_results_uids(self):
        html = (FIXTURES / "pe_search_results.html").read_text()
        uids = self.parser.extract_list(html, PE_SEARCH_SELECTORS["result_uids"])
        assert len(uids) == 2
        assert uids[0] == "24/00001/FUL"

    def test_next_page_link(self):
        html = (FIXTURES / "pe_search_results.html").read_text()
        next_el = self.parser.select_one(html, PE_SEARCH_SELECTORS["next_page"])
        assert next_el is not None

    def test_detail_extraction(self):
        html = (FIXTURES / "pe_detail.html").read_text()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        el = soup.select_one(PE_DETAIL_SELECTORS["reference"])
        assert el is not None
        span = el.find("span")
        if span:
            span.decompose()
        assert "24/00001/FUL" in el.get_text(strip=True)

    def test_dates_extraction(self):
        html = (FIXTURES / "pe_dates.html").read_text()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        el = soup.select_one(PE_DATES_SELECTORS["date_received"])
        assert el is not None


class TestPEGatherIds:
    async def test_gather_ids(self):
        html = (FIXTURES / "pe_search_results.html").read_text()
        last_page = html.replace(
            '<a href="/Northgate/PlanningExplorer/GeneralSearch.aspx?page=2"><img title="Go to next page" /></a>', ''
        )
        scraper = PlanningExplorerScraper(config=PE_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(return_value=last_page)
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=200, text=last_page, headers={}))
        scraper._client = mock_client
        results = await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))
        assert len(results) == 2
        assert results[0].uid == "24/00001/FUL"


class TestPEFetchDetail:
    async def test_fetch_detail(self):
        detail_html = (FIXTURES / "pe_detail.html").read_text()
        dates_html = (FIXTURES / "pe_dates.html").read_text()
        scraper = PlanningExplorerScraper(config=PE_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(side_effect=[detail_html, dates_html])
        scraper._client = mock_client
        app = ApplicationSummary(uid="24/00001/FUL", url="https://example.com/detail")
        detail = await scraper.fetch_detail(app)
        assert detail.reference == "24/00001/FUL"
        assert detail.application_type == "Full Planning Permission"
        assert detail.case_officer == "Jane Smith"
        assert detail.parish == "Testtown Parish"
