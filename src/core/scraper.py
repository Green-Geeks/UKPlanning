from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from src.core.config import CouncilConfig


@dataclass
class ApplicationSummary:
    """Minimal application data from search results."""

    uid: str
    url: Optional[str] = None


@dataclass
class ApplicationDetail:
    """Full application data from detail pages."""

    reference: str
    address: str
    description: str
    url: Optional[str] = None
    application_type: Optional[str] = None
    status: Optional[str] = None
    decision: Optional[str] = None
    date_received: Optional[date] = None
    date_validated: Optional[date] = None
    ward: Optional[str] = None
    parish: Optional[str] = None
    applicant_name: Optional[str] = None
    case_officer: Optional[str] = None
    raw_data: Dict = field(default_factory=dict)


@dataclass
class ScrapeResult:
    """Result of a scraping run."""

    date_from: date
    date_to: date
    applications: List[ApplicationDetail] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.error is None


class BaseScraper(ABC):
    """Abstract base for all platform and custom scrapers."""

    def __init__(self, config: CouncilConfig):
        self.config = config

    @abstractmethod
    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        """Discover application IDs/URLs in a date range."""

    @abstractmethod
    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        """Fetch full details for a single application."""

    async def scrape(self, date_from: date, date_to: date) -> ScrapeResult:
        """Full pipeline: gather IDs then fetch details for each."""
        try:
            summaries = await self.gather_ids(date_from, date_to)
            details = []
            for summary in summaries:
                detail = await self.fetch_detail(summary)
                details.append(detail)
            return ScrapeResult(date_from=date_from, date_to=date_to, applications=details)
        except Exception as e:
            return ScrapeResult(date_from=date_from, date_to=date_to, error=str(e))
