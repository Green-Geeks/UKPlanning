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
