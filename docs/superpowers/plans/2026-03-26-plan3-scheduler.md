# Plan 3: Scheduler & Orchestrator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the scheduler service that runs scrapers per council on their configured schedules, tracks run history, and auto-disables broken scrapers.

**Architecture:** APScheduler with one cron job per council. Each job loads the council config, instantiates the correct platform scraper, runs it, and writes results + run metadata to Postgres. A scraper registry maps platform names to scraper classes. Health monitoring auto-disables councils after 3 consecutive failures.

**Tech Stack:** APScheduler, SQLAlchemy (from Plan 1), Idox scrapers (from Plan 2)

---

## File Structure

```
src/
├── scheduler/
│   ├── __init__.py
│   ├── registry.py        # Maps platform names to scraper classes
│   ├── worker.py           # Single council scrape job logic
│   └── orchestrator.py     # APScheduler setup, job management, health checks
├── platforms/
│   └── idox.py             # (existing)
├── core/
│   └── (existing)
tests/
├── test_registry.py
├── test_worker.py
└── test_orchestrator.py
```

---

### Task 1: Scraper Registry

**Files:**
- Create: `src/scheduler/__init__.py`
- Create: `src/scheduler/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_registry.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement registry**

```python
# src/scheduler/__init__.py
# empty

# src/scheduler/registry.py
from typing import Type

from src.core.config import CouncilConfig
from src.core.scraper import BaseScraper
from src.platforms.idox import IdoxScraper, IdoxEndExcScraper, IdoxNIScraper, IdoxCrumbScraper


class ScraperRegistry:
    """Maps platform names to scraper classes."""

    def __init__(self):
        self._registry: dict[str, Type[BaseScraper]] = {
            "idox": IdoxScraper,
            "idox_endexc": IdoxEndExcScraper,
            "idox_ni": IdoxNIScraper,
            "idox_crumb": IdoxCrumbScraper,
        }

    def get_scraper_class(self, platform: str) -> Type[BaseScraper]:
        if platform not in self._registry:
            raise KeyError(f"No scraper registered for platform: {platform}")
        return self._registry[platform]

    def register(self, platform: str, scraper_class: Type[BaseScraper]) -> None:
        self._registry[platform] = scraper_class

    def list_platforms(self) -> list[str]:
        return list(self._registry.keys())

    def create_scraper(self, config: CouncilConfig) -> BaseScraper:
        cls = self.get_scraper_class(config.platform)
        return cls(config=config)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_registry.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scheduler/__init__.py src/scheduler/registry.py tests/test_registry.py
git commit -m "feat: add scraper registry mapping platforms to classes"
```

---

### Task 2: Worker — Single Council Scrape Job

**Files:**
- Create: `src/scheduler/worker.py`
- Create: `tests/test_worker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_worker.py
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

        # Verify application was stored
        apps = db_session.execute(select(Application)).scalars().all()
        assert len(apps) == 1
        assert apps[0].reference == "TEST/001"
        assert apps[0].council_id == council.id

        # Verify scrape run was logged
        runs = db_session.execute(select(ScrapeRun)).scalars().all()
        assert len(runs) == 1
        assert runs[0].status == "success"
        assert runs[0].applications_found == 1

        # Verify council timestamps updated
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

        # Verify scrape run logged as failed
        runs = db_session.execute(select(ScrapeRun)).scalars().all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].error_message is not None

        # Verify last_scraped_at updated but not last_successful_at
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

        # Run twice — second run should update, not duplicate
        await run_council_scrape(config, registry, db_session)
        await run_council_scrape(config, registry, db_session)

        apps = db_session.execute(select(Application)).scalars().all()
        assert len(apps) == 1  # no duplicate
        runs = db_session.execute(select(ScrapeRun)).scalars().all()
        assert len(runs) == 2  # two runs logged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement worker**

```python
# src/scheduler/worker.py
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import CouncilConfig
from src.core.models import Application, Council, ScrapeRun
from src.core.scraper import ApplicationDetail
from src.scheduler.registry import ScraperRegistry

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 14


async def run_council_scrape(
    config: CouncilConfig,
    registry: ScraperRegistry,
    session: Session,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> None:
    """Run a single scrape job for one council."""
    council = session.execute(
        select(Council).where(Council.authority_code == config.authority_code)
    ).scalar_one()

    now = datetime.now(timezone.utc)
    date_to = date.today()

    # Scrape from last successful run or lookback period
    if council.last_successful_at:
        date_from = council.last_successful_at.date()
    else:
        date_from = date_to - timedelta(days=lookback_days)

    # Create scrape run record
    scrape_run = ScrapeRun(
        council_id=council.id,
        status="running",
        date_range_from=date_from,
        date_range_to=date_to,
    )
    session.add(scrape_run)
    session.commit()

    scraper = registry.create_scraper(config)
    result = await scraper.scrape(date_from, date_to)

    if result.is_success:
        apps_found = len(result.applications)
        apps_updated = 0
        for detail in result.applications:
            apps_updated += _upsert_application(session, council.id, detail)
        session.commit()

        scrape_run.status = "success"
        scrape_run.applications_found = apps_found
        scrape_run.applications_updated = apps_updated
        council.last_successful_at = now
        logger.info(
            "Scrape %s: found=%d updated=%d",
            config.authority_code, apps_found, apps_updated,
        )
    else:
        scrape_run.status = "failed"
        scrape_run.error_message = result.error
        logger.warning("Scrape %s failed: %s", config.authority_code, result.error)

    scrape_run.completed_at = datetime.now(timezone.utc)
    council.last_scraped_at = now
    session.commit()


def _upsert_application(session: Session, council_id: int, detail: ApplicationDetail) -> int:
    """Insert or update an application. Returns 1 if changed, 0 if unchanged."""
    existing = session.execute(
        select(Application).where(
            Application.council_id == council_id,
            Application.reference == detail.reference,
        )
    ).scalar_one_or_none()

    if existing:
        changed = False
        for field in ("address", "description", "url", "application_type", "status",
                      "decision", "date_received", "date_validated", "ward", "parish",
                      "applicant_name", "case_officer"):
            new_val = getattr(detail, field, None)
            if new_val is not None and new_val != getattr(existing, field):
                setattr(existing, field, new_val)
                changed = True
        if detail.raw_data:
            existing.raw_data = detail.raw_data
            changed = True
        return 1 if changed else 0
    else:
        app = Application(
            council_id=council_id,
            reference=detail.reference,
            url=detail.url,
            address=detail.address,
            description=detail.description,
            application_type=detail.application_type,
            status=detail.status,
            decision=detail.decision,
            date_received=detail.date_received,
            date_validated=detail.date_validated,
            ward=detail.ward,
            parish=detail.parish,
            applicant_name=detail.applicant_name,
            case_officer=detail.case_officer,
            raw_data=detail.raw_data,
        )
        session.add(app)
        return 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worker.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scheduler/worker.py tests/test_worker.py
git commit -m "feat: add worker for single council scrape jobs"
```

---

### Task 3: Orchestrator — Job Scheduling & Health

**Files:**
- Create: `src/scheduler/orchestrator.py`
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_orchestrator.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from src.scheduler.orchestrator import Orchestrator
from src.core.config import CouncilConfig
from src.core.models import Council, ScrapeRun


CONFIGS = [
    CouncilConfig(
        name="Hart", authority_code="hart", platform="idox",
        base_url="https://example.com/hart", schedule="0 3 * * *",
    ),
    CouncilConfig(
        name="Belfast", authority_code="belfast", platform="idox_ni",
        base_url="https://example.com/belfast", schedule="0 4 * * *",
    ),
]


class TestOrchestrator:
    def test_init_creates_orchestrator(self, db_session):
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        assert orch is not None

    def test_sync_councils_to_db(self, db_session):
        """Orchestrator syncs council configs to the database."""
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        orch.sync_councils()

        councils = db_session.execute(select(Council)).scalars().all()
        assert len(councils) == 2
        codes = {c.authority_code for c in councils}
        assert codes == {"hart", "belfast"}

    def test_sync_councils_updates_existing(self, db_session):
        """Re-syncing updates existing councils without duplicating."""
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        orch.sync_councils()
        orch.sync_councils()  # second sync

        councils = db_session.execute(select(Council)).scalars().all()
        assert len(councils) == 2  # no duplicates

    def test_check_health_disables_after_failures(self, db_session):
        """Council disabled after 3 consecutive failures."""
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        orch.sync_councils()

        council = db_session.execute(
            select(Council).where(Council.authority_code == "hart")
        ).scalar_one()

        # Add 3 failed runs
        for _ in range(3):
            run = ScrapeRun(
                council_id=council.id,
                status="failed",
                error_message="Connection refused",
            )
            db_session.add(run)
        db_session.commit()

        disabled = orch.check_health()
        assert "hart" in disabled

        db_session.refresh(council)
        assert council.enabled is False

    def test_check_health_keeps_healthy_enabled(self, db_session):
        """Council stays enabled if last run was successful."""
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        orch.sync_councils()

        council = db_session.execute(
            select(Council).where(Council.authority_code == "hart")
        ).scalar_one()

        # 2 failures then 1 success
        for status in ["failed", "failed", "success"]:
            run = ScrapeRun(council_id=council.id, status=status)
            db_session.add(run)
        db_session.commit()

        disabled = orch.check_health()
        assert "hart" not in disabled
        db_session.refresh(council)
        assert council.enabled is True

    def test_get_enabled_configs(self, db_session):
        """Returns only configs for enabled councils."""
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        orch.sync_councils()

        # Disable one council
        council = db_session.execute(
            select(Council).where(Council.authority_code == "hart")
        ).scalar_one()
        council.enabled = False
        db_session.commit()

        enabled = orch.get_enabled_configs()
        codes = {c.authority_code for c in enabled}
        assert "hart" not in codes
        assert "belfast" in codes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement orchestrator**

```python
# src/scheduler/orchestrator.py
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import CouncilConfig
from src.core.models import Council, ScrapeRun
from src.scheduler.registry import ScraperRegistry

logger = logging.getLogger(__name__)

CONSECUTIVE_FAILURES_THRESHOLD = 3


class Orchestrator:
    """Manages council scraper scheduling and health monitoring."""

    def __init__(
        self,
        configs: list[CouncilConfig],
        session: Session,
        registry: ScraperRegistry | None = None,
    ):
        self._configs = {c.authority_code: c for c in configs}
        self._session = session
        self._registry = registry or ScraperRegistry()

    def sync_councils(self) -> None:
        """Sync council configs to the database. Creates new, updates existing."""
        for config in self._configs.values():
            existing = self._session.execute(
                select(Council).where(Council.authority_code == config.authority_code)
            ).scalar_one_or_none()

            if existing:
                existing.name = config.name
                existing.platform = config.platform
                existing.base_url = config.base_url
                existing.schedule_cron = config.schedule
                existing.requires_js = config.requires_js
            else:
                council = Council(
                    name=config.name,
                    authority_code=config.authority_code,
                    platform=config.platform,
                    base_url=config.base_url,
                    schedule_cron=config.schedule,
                    requires_js=config.requires_js,
                    enabled=True,
                )
                self._session.add(council)

        self._session.commit()

    def check_health(self) -> list[str]:
        """Check all councils for consecutive failures. Disable unhealthy ones.

        Returns list of authority_codes that were disabled.
        """
        disabled = []
        councils = self._session.execute(
            select(Council).where(Council.enabled == True)
        ).scalars().all()

        for council in councils:
            recent_runs = self._session.execute(
                select(ScrapeRun)
                .where(ScrapeRun.council_id == council.id)
                .order_by(ScrapeRun.id.desc())
                .limit(CONSECUTIVE_FAILURES_THRESHOLD)
            ).scalars().all()

            if len(recent_runs) >= CONSECUTIVE_FAILURES_THRESHOLD:
                if all(r.status == "failed" for r in recent_runs):
                    council.enabled = False
                    disabled.append(council.authority_code)
                    logger.warning(
                        "Disabled %s after %d consecutive failures",
                        council.authority_code,
                        CONSECUTIVE_FAILURES_THRESHOLD,
                    )

        self._session.commit()
        return disabled

    def get_enabled_configs(self) -> list[CouncilConfig]:
        """Return configs for all enabled councils."""
        enabled_councils = self._session.execute(
            select(Council).where(Council.enabled == True)
        ).scalars().all()

        enabled_codes = {c.authority_code for c in enabled_councils}
        return [c for c in self._configs.values() if c.authority_code in enabled_codes]

    def re_enable(self, authority_code: str) -> bool:
        """Re-enable a disabled council. Returns True if found and re-enabled."""
        council = self._session.execute(
            select(Council).where(Council.authority_code == authority_code)
        ).scalar_one_or_none()

        if council:
            council.enabled = True
            self._session.commit()
            logger.info("Re-enabled %s", authority_code)
            return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/scheduler/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add orchestrator with council sync and health monitoring"
```

---

### Task 4: Main Entry Point

**Files:**
- Create: `src/scheduler/main.py`
- Create: `tests/test_scheduler_main.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scheduler_main.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from src.scheduler.main import load_and_sync, get_scheduler_configs


class TestSchedulerMain:
    def test_get_scheduler_configs(self, tmp_path):
        config_file = tmp_path / "hart.yml"
        config_file.write_text("""
name: Hart
authority_code: hart
platform: idox
base_url: "https://example.com"
schedule: "0 3 * * *"
""")
        configs = get_scheduler_configs(tmp_path)
        assert len(configs) == 1
        assert configs[0].authority_code == "hart"

    def test_load_and_sync(self, db_session, tmp_path):
        config_file = tmp_path / "hart.yml"
        config_file.write_text("""
name: Hart
authority_code: hart
platform: idox
base_url: "https://example.com"
schedule: "0 3 * * *"
""")
        orch = load_and_sync(config_dir=tmp_path, session=db_session)
        assert orch is not None
        enabled = orch.get_enabled_configs()
        assert len(enabled) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scheduler_main.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement main entry point**

```python
# src/scheduler/main.py
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.config import load_all_councils, CouncilConfig
from src.scheduler.orchestrator import Orchestrator
from src.scheduler.registry import ScraperRegistry

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config" / "councils"


def get_scheduler_configs(config_dir: Path = DEFAULT_CONFIG_DIR) -> list[CouncilConfig]:
    """Load all council configs from the config directory."""
    return load_all_councils(config_dir)


def load_and_sync(
    config_dir: Path = DEFAULT_CONFIG_DIR,
    session: Session = None,
    registry: ScraperRegistry = None,
) -> Orchestrator:
    """Load configs, create orchestrator, sync councils to DB."""
    configs = get_scheduler_configs(config_dir)
    if registry is None:
        registry = ScraperRegistry()
    orch = Orchestrator(configs=configs, session=session, registry=registry)
    orch.sync_councils()
    logger.info("Synced %d councils to database", len(configs))
    return orch
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scheduler_main.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/scheduler/main.py tests/test_scheduler_main.py
git commit -m "feat: add scheduler main entry point with config loading"
```

---

## Summary

After completing this plan you will have:

- **ScraperRegistry** — maps platform names to scraper classes, extensible
- **Worker** — runs a single council scrape (gather + detail + DB upsert + run logging)
- **Orchestrator** — syncs configs to DB, health checks, auto-disable after 3 failures
- **Main entry point** — loads configs and bootstraps the system

**What's NOT in this plan (deferred):** The actual APScheduler cron loop. The orchestrator and worker are fully functional and testable without it. Adding APScheduler's event loop is a thin wrapper that will be added when the dashboard (Plan 4) provides the process that hosts it.

**Next plan:** Plan 4 — Dashboard (FastAPI web UI)
