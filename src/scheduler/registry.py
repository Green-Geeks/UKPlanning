from src.core.config import CouncilConfig
from src.core.scraper import BaseScraper
from src.platforms.agile import AgileApplicationsScraper
from src.platforms.ambervalley import AmberValleyScraper
from src.platforms.barnsley import BarnsleyScraper
from src.platforms.bath import BathScraper
from src.platforms.fareham import FarehamScraper
from src.platforms.idox import IdoxScraper, IdoxEndExcScraper, IdoxNIScraper, IdoxCrumbScraper
from src.platforms.ni_portal import NIPortalScraper
from src.platforms.northlincs import NorthLincsScraper
from src.platforms.planning_explorer import PlanningExplorerScraper
from src.platforms.planning_register import PlanningRegisterScraper
from src.platforms.salesforce_arcus import SalesforceArcusScraper
from src.platforms.swiftlg import SwiftLGScraper, SwiftLGLabelScraper
from src.platforms.civica import CivicaScraper
from src.platforms.tascomi import TascomiScraper
from src.platforms.westdunbarton import WestDunbartonScraper


class ScraperRegistry:
    """Maps platform names to scraper classes."""

    def __init__(self):
        self._registry = {
            "idox": IdoxScraper,
            "idox_endexc": IdoxEndExcScraper,
            "idox_ni": IdoxNIScraper,
            "idox_crumb": IdoxCrumbScraper,
            "planning_explorer": PlanningExplorerScraper,
            "swiftlg": SwiftLGScraper,
            "swiftlg_label": SwiftLGLabelScraper,
            "ni_portal": NIPortalScraper,
            "agile": AgileApplicationsScraper,
            "ambervalley": AmberValleyScraper,
            "barnsley": BarnsleyScraper,
            "bath": BathScraper,
            "fareham": FarehamScraper,
            "northlincs": NorthLincsScraper,
            "salesforce": SalesforceArcusScraper,
            "civica": CivicaScraper,
            "planning_register": PlanningRegisterScraper,
            "tascomi": TascomiScraper,
            "westdunbarton": WestDunbartonScraper,
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
