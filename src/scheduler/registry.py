from src.core.config import CouncilConfig
from src.core.scraper import BaseScraper
from src.platforms.idox import IdoxScraper, IdoxEndExcScraper, IdoxNIScraper, IdoxCrumbScraper


class ScraperRegistry:
    """Maps platform names to scraper classes."""

    def __init__(self):
        self._registry = {
            "idox": IdoxScraper,
            "idox_endexc": IdoxEndExcScraper,
            "idox_ni": IdoxNIScraper,
            "idox_crumb": IdoxCrumbScraper,
        }

    def get_scraper_class(self, platform):
        if platform not in self._registry:
            raise KeyError(f"No scraper registered for platform: {platform}")
        return self._registry[platform]

    def register(self, platform, scraper_class):
        self._registry[platform] = scraper_class

    def list_platforms(self):
        return list(self._registry.keys())

    def create_scraper(self, config):
        cls = self.get_scraper_class(config.platform)
        return cls(config=config)
