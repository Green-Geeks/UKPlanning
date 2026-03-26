import pytest
from pathlib import Path
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from src.platforms.swiftlg import SwiftLGScraper, SWIFTLG_SEARCH_SELECTORS, SWIFTLG_SPAN_SELECTORS
from src.core.config import CouncilConfig
from src.core.parser import PageParser
from src.core.scraper import ApplicationSummary

FIXTURES = Path(__file__).parent / "fixtures"
SWIFTLG_CONFIG = CouncilConfig(
    name="Dudley", authority_code="dudley", platform="swiftlg",
    base_url="https://www5.dudley.gov.uk/swiftlg/apas/run",
)


class TestSwiftLGSelectors:
    def setup_method(self):
        self.parser = PageParser()

    def test_search_results_links(self):
        html = (FIXTURES / "swiftlg_search_results.html").read_text()
        links = self.parser.extract_list(html, SWIFTLG_SEARCH_SELECTORS["result_links"], attr="href")
        assert len(links) == 2

    def test_search_results_uids(self):
        html = (FIXTURES / "swiftlg_search_results.html").read_text()
        uids = self.parser.extract_list(html, SWIFTLG_SEARCH_SELECTORS["result_uids"])
        assert len(uids) == 2
        assert uids[0] == "24/00001/FUL"

    def test_detail_extraction(self):
        html = (FIXTURES / "swiftlg_detail.html").read_text()
        data = self.parser.extract(html, SWIFTLG_SPAN_SELECTORS)
        assert data["reference"] is not None
        assert data["description"] is not None


class TestSwiftLGGatherIds:
    async def test_gather_ids(self):
        last_page = (FIXTURES / "swiftlg_search_results.html").read_text()
        last_page = last_page.replace('Pages <a href="?StartIndex=11">2</a>', 'Pages')
        scraper = SwiftLGScraper(config=SWIFTLG_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(return_value=last_page)
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=200, text=last_page, headers={}))
        scraper._client = mock_client
        results = await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))
        assert len(results) == 2
        assert results[0].uid == "24/00001/FUL"


class TestSwiftLGFetchDetail:
    async def test_fetch_detail(self):
        detail_html = (FIXTURES / "swiftlg_detail.html").read_text()
        scraper = SwiftLGScraper(config=SWIFTLG_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(return_value=detail_html)
        scraper._client = mock_client
        app = ApplicationSummary(uid="24/00001/FUL", url="https://example.com/detail")
        detail = await scraper.fetch_detail(app)
        assert detail.reference == "24/00001/FUL"
        assert "123 High Street" in detail.address
        assert detail.description == "Erection of single storey rear extension"
