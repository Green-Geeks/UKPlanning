import pytest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from src.scheduler.worker import run_council_scrape
from src.scheduler.registry import ScraperRegistry
from src.core.config import CouncilConfig
from src.core.scraper import ApplicationSummary, ApplicationDetail, ScrapeResult, BaseScraper
from src.core.models import Council, Application, ScrapeRun


class FakeScraper(BaseScraper):
    async def gather_ids(self, date_from, date_to):
        return [
            ApplicationSummary(uid="TEST/001", url="https://example.com/app/1"),
        ]

    async def fetch_detail(self, application):
        return ApplicationDetail(
            reference=application.uid,
            address="123 Test Street",
            description="Test application",
            url=application.url,
            application_type="Full",
            status="Pending",
            raw_data={"extra": "data"},
        )


class FailingScraper(BaseScraper):
    async def gather_ids(self, date_from, date_to):
        raise ConnectionError("Connection refused")

    async def fetch_detail(self, application):
        pass


class TestRunCouncilScrape:
    def _setup_council(self, db_session):
        council = Council(
            name="TestCouncil",
            authority_code="test",
            platform="fake",
            base_url="https://example.com",
            schedule_cron="0 3 * * *",
            enabled=True,
        )
        db_session.add(council)
        db_session.commit()
        return council

    async def test_successful_scrape(self, db_session):
        council = self._setup_council(db_session)
        registry = ScraperRegistry()
        registry.register("fake", FakeScraper)

        config = CouncilConfig(
            name="TestCouncil", authority_code="test",
            platform="fake", base_url="https://example.com",
        )

        await run_council_scrape(config, registry, db_session)

        apps = db_session.execute(select(Application)).scalars().all()
        assert len(apps) == 1
        assert apps[0].reference == "TEST/001"
        assert apps[0].council_id == council.id

        runs = db_session.execute(select(ScrapeRun)).scalars().all()
        assert len(runs) == 1
        assert runs[0].status == "success"
        assert runs[0].applications_found == 1

        db_session.refresh(council)
        assert council.last_scraped_at is not None
        assert council.last_successful_at is not None

    async def test_failed_scrape(self, db_session):
        council = self._setup_council(db_session)
        registry = ScraperRegistry()
        registry.register("fake", FailingScraper)

        config = CouncilConfig(
            name="TestCouncil", authority_code="test",
            platform="fake", base_url="https://example.com",
        )

        await run_council_scrape(config, registry, db_session)

        runs = db_session.execute(select(ScrapeRun)).scalars().all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].error_message is not None

        db_session.refresh(council)
        assert council.last_scraped_at is not None
        assert council.last_successful_at is None

    async def test_duplicate_application_updates(self, db_session):
        council = self._setup_council(db_session)
        registry = ScraperRegistry()
        registry.register("fake", FakeScraper)

        config = CouncilConfig(
            name="TestCouncil", authority_code="test",
            platform="fake", base_url="https://example.com",
        )

        await run_council_scrape(config, registry, db_session)
        await run_council_scrape(config, registry, db_session)

        apps = db_session.execute(select(Application)).scalars().all()
        assert len(apps) == 1  # no duplicate
        runs = db_session.execute(select(ScrapeRun)).scalars().all()
        assert len(runs) == 2  # two runs logged
