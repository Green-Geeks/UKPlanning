#!/usr/bin/env python3
"""Main entry point: starts dashboard with API triggers for scraping.

Usage:
    python run_server.py                     # Start dashboard (no auto-scraping)
    python run_server.py --scrape-once hart  # Scrape one council and exit

Scraping is triggered via the dashboard API:
    POST /api/scrape/{authority_code}        # Scrape one council
    POST /api/scrape-all                     # Scrape all enabled councils
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from sqlalchemy import select, func

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
    engine = get_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    return engine


async def scrape_once(authority_code: str):
    """Scrape a single council and exit (CLI mode)."""
    engine = setup_db()
    Session = get_session_factory(engine)
    session = Session()

    configs = load_all_councils(CONFIG_DIR)
    config = next((c for c in configs if c.authority_code == authority_code), None)
    if not config:
        logger.error("Council '%s' not found in configs", authority_code)
        sys.exit(1)

    registry = ScraperRegistry()
    load_and_sync(config_dir=CONFIG_DIR, session=session, registry=registry)

    logger.info("Scraping %s...", config.name)
    await run_council_scrape(config, registry, session)
    logger.info("Done.")
    session.close()


def run_server():
    """Start dashboard with scrape trigger API endpoints."""
    engine = setup_db()
    session_factory = get_session_factory(engine)

    configs = load_all_councils(CONFIG_DIR)
    registry = ScraperRegistry()

    session = session_factory()
    load_and_sync(config_dir=CONFIG_DIR, session=session, registry=registry)
    session.close()

    configs_by_code = {c.authority_code: c for c in configs}
    # Track running scrapes to prevent duplicates
    running_scrapes: set[str] = set()
    # Track asyncio tasks so they can be cancelled
    scrape_tasks: set[asyncio.Task] = set()

    app = create_app()

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # --- API endpoints for triggering scrapes ---

    from fastapi import Depends
    from fastapi.responses import JSONResponse
    from sqlalchemy.orm import Session

    @app.post("/api/scrape/{authority_code}")
    async def trigger_scrape(authority_code: str, days: int = 0, db: Session = Depends(get_db)):
        """Trigger a scrape for a single council. Runs in background.

        Args:
            days: Force a specific lookback period in days (0 = use default logic).
        """
        config = configs_by_code.get(authority_code)
        if not config:
            return JSONResponse({"error": f"Council '{authority_code}' not found"}, status_code=404)
        if authority_code in running_scrapes:
            return JSONResponse({"error": f"Scrape already running for '{authority_code}'"}, status_code=409)

        lookback = days if days > 0 else None

        async def do_scrape():
            running_scrapes.add(authority_code)
            try:
                session = session_factory()
                try:
                    if lookback:
                        await run_council_scrape(config, registry, session, lookback_days=lookback)
                    else:
                        await run_council_scrape(config, registry, session)
                finally:
                    session.close()
            finally:
                running_scrapes.discard(authority_code)

        task = asyncio.create_task(do_scrape())
        scrape_tasks.add(task)
        task.add_done_callback(scrape_tasks.discard)
        return {"status": "started", "council": config.name, "authority_code": authority_code, "lookback_days": lookback or "default"}

    @app.post("/api/scrape-all")
    async def trigger_scrape_all(concurrency: int = 8, days: int = 0, db: Session = Depends(get_db)):
        """Trigger scrape for all enabled councils. Runs concurrently in background.

        Args:
            concurrency: Number of scrapers to run in parallel (default 8, max 20).
            days: Force a specific lookback period in days (0 = use default logic).
        """
        from src.scheduler.orchestrator import Orchestrator
        concurrency = max(1, min(concurrency, 20))
        lookback = days if days > 0 else None

        session = session_factory()
        orch = Orchestrator(configs=configs, session=session, registry=registry)
        enabled = orch.get_enabled_configs()
        session.close()

        already_running = [c.authority_code for c in enabled if c.authority_code in running_scrapes]
        to_scrape = [c for c in enabled if c.authority_code not in running_scrapes]

        semaphore = asyncio.Semaphore(concurrency)

        async def scrape_one(config):
            async with semaphore:
                running_scrapes.add(config.authority_code)
                try:
                    session = session_factory()
                    try:
                        logger.info("Scraping %s...", config.name)
                        if lookback:
                            await run_council_scrape(config, registry, session, lookback_days=lookback)
                        else:
                            await run_council_scrape(config, registry, session)
                    except Exception as e:
                        logger.error("Error scraping %s: %s", config.name, e)
                    finally:
                        session.close()
                finally:
                    running_scrapes.discard(config.authority_code)

        async def do_scrape_all():
            await asyncio.gather(*(scrape_one(c) for c in to_scrape))

        task = asyncio.create_task(do_scrape_all())
        scrape_tasks.add(task)
        task.add_done_callback(scrape_tasks.discard)
        return {
            "status": "started",
            "councils_queued": len(to_scrape),
            "concurrency": concurrency,
            "already_running": already_running,
        }

    @app.post("/api/scrape-stop")
    async def stop_all_scrapes():
        """Cancel all running/queued scrape tasks and clear stale DB records."""
        cancelled = list(running_scrapes)
        for task in list(scrape_tasks):
            task.cancel()
        scrape_tasks.clear()
        running_scrapes.clear()

        # Clear stale "running" ScrapeRun records in DB (e.g. from a Docker restart)
        from src.core.models import ScrapeRun
        session = session_factory()
        stale = session.execute(
            select(ScrapeRun).where(ScrapeRun.status == "running")
        ).scalars().all()
        for run in stale:
            run.status = "failed"
            run.error_message = "Cancelled by user"
            run.completed_at = datetime.now(timezone.utc)
        session.commit()
        session.close()

        logger.info("Stopped %d running scrapes, cleared %d stale DB records", len(cancelled), len(stale))
        return {"status": "stopped", "cancelled": cancelled, "stale_cleared": len(stale)}

    @app.get("/api/scrape-status")
    async def scrape_status():
        """Check which scrapes are currently running (in-memory + DB)."""
        from src.core.models import ScrapeRun
        session = session_factory()
        stale_count = session.execute(
            select(func.count(ScrapeRun.id)).where(ScrapeRun.status == "running")
        ).scalar()
        session.close()
        return {
            "running": sorted(running_scrapes),
            "count": len(running_scrapes),
            "stale": max(0, stale_count - len(running_scrapes)),
        }

    logger.info("Starting UK Planning Dashboard")
    logger.info("  Councils loaded: %d", len(configs))
    logger.info("  Dashboard: http://0.0.0.0:8000")
    logger.info("  Trigger scrape: POST /api/scrape/{authority_code}")
    logger.info("  Trigger all:    POST /api/scrape-all")

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UK Planning Scraper")
    parser.add_argument("--scrape-once", metavar="CODE", help="Scrape one council and exit")
    args = parser.parse_args()

    if args.scrape_once:
        asyncio.run(scrape_once(args.scrape_once))
    else:
        run_server()
