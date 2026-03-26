import pytest
from datetime import date
from pathlib import Path
from sqlalchemy import select

from src.core.parser import PageParser
from src.core.browser import HttpClient
from src.core.config import CouncilConfig, load_council_config
from src.core.scraper import ApplicationSummary, ApplicationDetail, BaseScraper, ScrapeResult
from src.core.models import Council, Application, ScrapeRun


SAMPLE_CONFIG_YAML = """
name: TestCouncil
authority_code: test_council
platform: idox
base_url: "https://example.com/planning"
schedule: "0 3 * * *"
selectors:
  reference: "th:-soup-contains('Reference') + td"
  address: "th:-soup-contains('Address') + td"
  description: "th:-soup-contains('Proposal') + td"
"""


class FakeScraper(BaseScraper):
    """Concrete scraper for testing the full flow."""

    async def gather_ids(self, date_from, date_to):
        return [
            ApplicationSummary(uid="TEST/001", url="https://example.com/app/1"),
            ApplicationSummary(uid="TEST/002", url="https://example.com/app/2"),
        ]

    async def fetch_detail(self, application):
        return ApplicationDetail(
            reference=application.uid,
            address="123 Test Street",
            description="Test application",
            url=application.url,
        )


class TestIntegration:
    def test_config_to_scraper_flow(self, tmp_path):
        config_file = tmp_path / "test.yml"
        config_file.write_text(SAMPLE_CONFIG_YAML)
        config = load_council_config(config_file)
        scraper = FakeScraper(config=config)
        assert scraper.config.name == "TestCouncil"

    @pytest.mark.asyncio
    async def test_scraper_full_pipeline(self):
        config = CouncilConfig(
            name="TestCouncil",
            authority_code="test",
            platform="idox",
            base_url="https://example.com",
        )
        scraper = FakeScraper(config=config)
        result = await scraper.scrape(date(2024, 1, 1), date(2024, 1, 14))
        assert result.is_success
        assert len(result.applications) == 2
        assert result.applications[0].reference == "TEST/001"

    def test_parser_extracts_from_html(self):
        parser = PageParser()
        html = """
        <table>
          <tr><th>Reference</th><td>24/001</td></tr>
          <tr><th>Address</th><td>123 High St</td></tr>
          <tr><th>Proposal</th><td>New house</td></tr>
        </table>
        """
        selectors = {
            "reference": "th:-soup-contains('Reference') + td",
            "address": "th:-soup-contains('Address') + td",
            "description": "th:-soup-contains('Proposal') + td",
        }
        result = parser.extract(html, selectors)
        assert result["reference"] == "24/001"

    def test_scrape_result_to_db_model(self, db_session):
        council = Council(
            name="TestCouncil",
            authority_code="test",
            platform="idox",
            base_url="https://example.com",
        )
        db_session.add(council)
        db_session.commit()

        detail = ApplicationDetail(
            reference="24/001",
            address="123 High St",
            description="New house",
            raw_data={"extra": "data"},
        )
        app = Application(
            council_id=council.id,
            reference=detail.reference,
            address=detail.address,
            description=detail.description,
            raw_data=detail.raw_data,
        )
        db_session.add(app)
        db_session.commit()

        result = db_session.execute(select(Application)).scalar_one()
        assert result.reference == "24/001"
        assert result.council_id == council.id
