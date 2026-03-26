import pytest
from pathlib import Path
from src.core.parser import PageParser
from src.core.config import CouncilConfig, load_all_councils
from src.platforms.idox import IDOX_SELECTORS, IDOX_DATES_SELECTORS, IDOX_INFO_SELECTORS, IDOX_SEARCH_SELECTORS

FIXTURES = Path(__file__).parent / "fixtures"


class TestIdoxSelectors:
    def setup_method(self):
        self.parser = PageParser()

    def test_search_results_extraction(self):
        html = (FIXTURES / "idox_search_results.html").read_text()
        results = self.parser.extract_list(html, IDOX_SEARCH_SELECTORS["result_links"], attr="href")
        assert len(results) == 2
        assert "ABC123" in results[0]
        assert "DEF456" in results[1]

    def test_search_results_uids(self):
        html = (FIXTURES / "idox_search_results.html").read_text()
        uids = self.parser.extract_list(html, IDOX_SEARCH_SELECTORS["result_uids"])
        assert len(uids) == 2
        assert uids[0] == "24/00001/FUL"
        assert uids[1] == "24/00002/HOU"

    def test_search_next_page(self):
        html = (FIXTURES / "idox_search_results.html").read_text()
        next_link = self.parser.select_one(html, IDOX_SEARCH_SELECTORS["next_page"])
        assert next_link is not None
        assert "page=2" in next_link["href"]

    def test_summary_page_extraction(self):
        html = (FIXTURES / "idox_detail_summary.html").read_text()
        data = self.parser.extract(html, IDOX_SELECTORS)
        assert data["reference"] == "24/00001/FUL"
        assert data["address"] == "123 High Street, Testtown, TT1 1AA"
        assert data["description"] == "Erection of single storey rear extension"
        assert data["status"] == "Awaiting decision"

    def test_dates_page_extraction(self):
        html = (FIXTURES / "idox_detail_dates.html").read_text()
        data = self.parser.extract(html, IDOX_DATES_SELECTORS)
        assert data["date_validated"] is not None
        assert "16 Jan 2024" in data["date_validated"]

    def test_info_page_extraction(self):
        html = (FIXTURES / "idox_detail_info.html").read_text()
        data = self.parser.extract(html, IDOX_INFO_SELECTORS)
        assert data["application_type"] == "Full Planning Permission"
        assert data["case_officer"] == "John Smith"
        assert data["parish"] == "Testtown Parish Council"
        assert data["ward"] == "Testtown Ward"
        assert data["applicant_name"] == "Mr J Doe"

    def test_tab_links_extraction(self):
        html = (FIXTURES / "idox_detail_summary.html").read_text()
        dates_link = self.parser.select_one(html, IDOX_SEARCH_SELECTORS["dates_tab"])
        info_link = self.parser.select_one(html, IDOX_SEARCH_SELECTORS["info_tab"])
        assert dates_link is not None
        assert "activeTab=dates" in dates_link["href"]
        assert info_link is not None
        assert "activeTab=details" in info_link["href"]


from datetime import date
from unittest.mock import AsyncMock, MagicMock
from src.platforms.idox import IdoxScraper
from src.core.scraper import ApplicationSummary

SEARCH_RESULTS_LAST_PAGE = """
<html><body>
<p class="pager top">
  <span class="showing">Showing 11-12 of 12</span>
</p>
<ul id="searchresults">
  <li class="searchresult">
    <a href="/online-applications/applicationDetails.do?activeTab=summary&amp;keyVal=GHI789">
      <span>View</span>
    </a>
    <p class="metainfo">
      No: <span>24/00003/LBC</span> |
      Received: <span>Fri 19 Jan 2024</span>
    </p>
    <p class="address">789 Church Lane, Testbury</p>
    <p class="description">Listed building consent for window replacement</p>
  </li>
</ul>
</body></html>
"""

IDOX_CONFIG = CouncilConfig(
    name="Hart",
    authority_code="hart",
    platform="idox",
    base_url="https://publicaccess.hart.gov.uk/online-applications",
)


class TestIdoxGatherIds:
    async def test_gather_ids_single_page(self):
        scraper = IdoxScraper(config=IDOX_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(return_value=SEARCH_RESULTS_LAST_PAGE)
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            text=SEARCH_RESULTS_LAST_PAGE,
            headers={},
        ))
        scraper._client = mock_client

        results = await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))
        assert len(results) == 1
        assert results[0].uid == "24/00003/LBC"
        assert "GHI789" in results[0].url

    async def test_gather_ids_with_pagination(self):
        SEARCH_RESULTS_HTML = (FIXTURES / "idox_search_results.html").read_text()
        scraper = IdoxScraper(config=IDOX_CONFIG)
        mock_client = AsyncMock()

        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            text=SEARCH_RESULTS_HTML,
            headers={},
        ))
        mock_client.get_html = AsyncMock(side_effect=[
            SEARCH_RESULTS_HTML,       # search page load
            SEARCH_RESULTS_LAST_PAGE,  # page 2
        ])
        scraper._client = mock_client

        results = await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))
        assert len(results) == 3  # 2 from page 1 + 1 from page 2

    async def test_gather_ids_empty_results(self):
        scraper = IdoxScraper(config=IDOX_CONFIG)
        mock_client = AsyncMock()
        empty_html = '<html><body><ul id="searchresults"></ul></body></html>'
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            text=empty_html,
            headers={},
        ))
        mock_client.get_html = AsyncMock(return_value=empty_html)
        scraper._client = mock_client

        results = await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))
        assert results == []
