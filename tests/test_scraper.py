import pytest
from datetime import date
from src.core.scraper import (
    ApplicationSummary,
    ApplicationDetail,
    ScrapeResult,
    BaseScraper,
)
from src.core.config import CouncilConfig


DUMMY_CONFIG = CouncilConfig(
    name="TestCouncil",
    authority_code="test",
    platform="test_platform",
    base_url="https://example.com",
)


class TestDataTypes:
    def test_application_summary(self):
        summary = ApplicationSummary(uid="24/001", url="https://example.com/app/1")
        assert summary.uid == "24/001"
        assert summary.url == "https://example.com/app/1"

    def test_application_detail(self):
        detail = ApplicationDetail(
            reference="24/001",
            address="123 High Street",
            description="New dwelling",
            url="https://example.com/app/1",
            raw_data={"extra": "field"},
        )
        assert detail.reference == "24/001"
        assert detail.raw_data["extra"] == "field"

    def test_application_detail_optional_fields(self):
        detail = ApplicationDetail(reference="24/001", address="addr", description="desc")
        assert detail.application_type is None
        assert detail.ward is None
        assert detail.raw_data == {}

    def test_scrape_result_success(self):
        result = ScrapeResult(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 14),
            applications=[
                ApplicationDetail(reference="24/001", address="addr", description="desc"),
            ],
        )
        assert result.is_success is True
        assert result.error is None
        assert len(result.applications) == 1

    def test_scrape_result_failure(self):
        result = ScrapeResult(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 14),
            applications=[],
            error="Connection timeout",
        )
        assert result.is_success is False


class TestBaseScraper:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseScraper(config=DUMMY_CONFIG)

    def test_subclass_must_implement_gather_ids(self):
        class BadScraper(BaseScraper):
            pass

        with pytest.raises(TypeError):
            BadScraper(config=DUMMY_CONFIG)

    def test_subclass_with_methods_can_instantiate(self):
        class GoodScraper(BaseScraper):
            async def gather_ids(self, date_from, date_to):
                return []

            async def fetch_detail(self, application):
                return ApplicationDetail(reference="x", address="x", description="x")

        scraper = GoodScraper(config=DUMMY_CONFIG)
        assert scraper.config.authority_code == "test"
