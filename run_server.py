#!/usr/bin/env python3
"""Main entry point: starts dashboard + scheduler.

Usage:
    python run_server.py                    # Start dashboard + scheduler
    python run_server.py --dashboard-only   # Dashboard only (no scraping)
    python run_server.py --scrape-once hart  # Scrape one council and exit
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

from src.core.config import load_all_councils
from src.core.database import get_engine, get_session_factory
from src.core.models import Base
from src.dashboard.app import create_app
from src.dashboard.dependencies import get_db
from src.scheduler.main import load_and_sync
from src.scheduler.registry import ScraperRegistry
from src.scheduler.worker import run_council_scrape

logging.basicConfig(
    format="%(name)s %(levelname)s [%(asctime)s]: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("ukplanning")

CONFIG_DIR = Path(__file__).parent / "src" / "config" / "councils"
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ukplanning:devpassword@localhost:5432/ukplanning",
)


def setup_db():
    """Create engine and ensure tables exist."""
    engine = get_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    return engine


async def scrape_once(authority_code: str):
    """Scrape a single council and exit."""
    engine = setup_db()
    Session = get_session_factory(engine)
    session = Session()

    configs = load_all_councils(CONFIG_DIR)
    config = next((c for c in configs if c.authority_code == authority_code), None)
    if not config:
        logger.error("Council '%s' not found in configs", authority_code)
        sys.exit(1)

    registry = ScraperRegistry()
    orch = load_and_sync(config_dir=CONFIG_DIR, session=session, registry=registry)

    logger.info("Scraping %s...", config.name)
    await run_council_scrape(config, registry, session)
    logger.info("Done.")
    session.close()


async def run_scheduler(session_factory, registry, configs, interval_minutes=60):
    """Simple async scheduler loop — scrapes all enabled councils periodically."""
    while True:
        Session = session_factory
        session = Session()
        try:
            from src.scheduler.orchestrator import Orchestrator
            orch = Orchestrator(configs=configs, session=session, registry=registry)
            enabled = orch.get_enabled_configs()
            logger.info("Starting scrape cycle: %d enabled councils", len(enabled))

            for config in enabled:
                try:
                    logger.info("Scraping %s...", config.name)
                    await run_council_scrape(config, registry, session)
                except Exception as e:
                    logger.error("Error scraping %s: %s", config.name, e)

            disabled = orch.check_health()
            if disabled:
                logger.warning("Disabled councils: %s", ", ".join(disabled))

            logger.info("Scrape cycle complete. Sleeping %d minutes.", interval_minutes)
        finally:
            session.close()

        await asyncio.sleep(interval_minutes * 60)


def run_dashboard_with_scheduler():
    """Start FastAPI dashboard with background scheduler."""
    engine = setup_db()
    session_factory = get_session_factory(engine)

    configs = load_all_councils(CONFIG_DIR)
    registry = ScraperRegistry()

    # Sync councils to DB
    session = session_factory()
    load_and_sync(config_dir=CONFIG_DIR, session=session, registry=registry)
    session.close()

    app = create_app()

    # Override DB dependency to use our engine
    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Start scheduler as background task on startup
    @app.on_event("startup")
    async def start_scheduler():
        asyncio.create_task(
            run_scheduler(session_factory, registry, configs)
        )

    logger.info("Starting UK Planning Dashboard + Scheduler")
    logger.info("  Councils loaded: %d", len(configs))
    logger.info("  Dashboard: http://0.0.0.0:8000")
    logger.info("  Database: %s", DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL)

    uvicorn.run(app, host="0.0.0.0", port=8000)


def run_dashboard_only():
    """Start FastAPI dashboard without scheduler."""
    engine = setup_db()
    session_factory = get_session_factory(engine)

    configs = load_all_councils(CONFIG_DIR)
    session = session_factory()
    load_and_sync(config_dir=CONFIG_DIR, session=session)
    session.close()

    app = create_app()

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    logger.info("Starting UK Planning Dashboard (no scheduler)")
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UK Planning Scraper")
    parser.add_argument("--dashboard-only", action="store_true", help="Dashboard only, no scraping")
    parser.add_argument("--scrape-once", metavar="CODE", help="Scrape one council and exit")
    args = parser.parse_args()

    if args.scrape_once:
        asyncio.run(scrape_once(args.scrape_once))
    elif args.dashboard_only:
        run_dashboard_only()
    else:
        run_dashboard_with_scheduler()
