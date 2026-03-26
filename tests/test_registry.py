import pytest
from src.scheduler.registry import ScraperRegistry
from src.platforms.idox import IdoxScraper, IdoxEndExcScraper, IdoxNIScraper, IdoxCrumbScraper
from src.core.config import CouncilConfig
from src.core.scraper import BaseScraper


class TestScraperRegistry:
    def test_get_idox_scraper(self):
        registry = ScraperRegistry()
        cls = registry.get_scraper_class("idox")
        assert cls is IdoxScraper

    def test_get_idox_variants(self):
        registry = ScraperRegistry()
        assert registry.get_scraper_class("idox_endexc") is IdoxEndExcScraper
        assert registry.get_scraper_class("idox_ni") is IdoxNIScraper
        assert registry.get_scraper_class("idox_crumb") is IdoxCrumbScraper

    def test_unknown_platform_raises(self):
        registry = ScraperRegistry()
        with pytest.raises(KeyError, match="unknown_platform"):
            registry.get_scraper_class("unknown_platform")

    def test_register_custom_scraper(self):
        registry = ScraperRegistry()

        class MyScraper(BaseScraper):
            async def gather_ids(self, date_from, date_to):
                return []
            async def fetch_detail(self, application):
                pass

        registry.register("custom_test", MyScraper)
        assert registry.get_scraper_class("custom_test") is MyScraper

    def test_list_platforms(self):
        registry = ScraperRegistry()
        platforms = registry.list_platforms()
        assert "idox" in platforms
        assert "idox_endexc" in platforms
        assert "idox_ni" in platforms
        assert "idox_crumb" in platforms

    def test_create_scraper_instance(self):
        registry = ScraperRegistry()
        config = CouncilConfig(
            name="Hart", authority_code="hart", platform="idox",
            base_url="https://example.com",
        )
        scraper = registry.create_scraper(config)
        assert isinstance(scraper, IdoxScraper)
        assert scraper.config.authority_code == "hart"
