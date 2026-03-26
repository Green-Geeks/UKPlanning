import logging
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import CouncilConfig
from src.core.models import Council, ScrapeRun
from src.scheduler.registry import ScraperRegistry

logger = logging.getLogger(__name__)

CONSECUTIVE_FAILURES_THRESHOLD = 3


class Orchestrator:
    def __init__(self, configs, session, registry=None):
        self._configs = {c.authority_code: c for c in configs}
        self._session = session
        self._registry = registry or ScraperRegistry()

    def sync_councils(self):
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

    def check_health(self):
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
                    logger.warning("Disabled %s after %d consecutive failures",
                                   council.authority_code, CONSECUTIVE_FAILURES_THRESHOLD)
        self._session.commit()
        return disabled

    def get_enabled_configs(self):
        enabled_councils = self._session.execute(
            select(Council).where(Council.enabled == True)
        ).scalars().all()
        enabled_codes = {c.authority_code for c in enabled_councils}
        return [c for c in self._configs.values() if c.authority_code in enabled_codes]

    def re_enable(self, authority_code):
        council = self._session.execute(
            select(Council).where(Council.authority_code == authority_code)
        ).scalar_one_or_none()
        if council:
            council.enabled = True
            self._session.commit()
            return True
        return False
