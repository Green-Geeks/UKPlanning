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
    config,
    registry,
    session,
    lookback_days=DEFAULT_LOOKBACK_DAYS,
):
    """Run a single scrape job for one council."""
    council = session.execute(
        select(Council).where(Council.authority_code == config.authority_code)
    ).scalar_one()

    now = datetime.now(timezone.utc)
    date_to = date.today()

    if council.last_successful_at:
        date_from = council.last_successful_at.date()
    else:
        date_from = date_to - timedelta(days=lookback_days)

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


def _upsert_application(session, council_id, detail):
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
