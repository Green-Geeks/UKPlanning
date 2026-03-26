import pytest
from datetime import datetime, timezone
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
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        orch.sync_councils()
        councils = db_session.execute(select(Council)).scalars().all()
        assert len(councils) == 2
        codes = {c.authority_code for c in councils}
        assert codes == {"hart", "belfast"}

    def test_sync_councils_updates_existing(self, db_session):
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        orch.sync_councils()
        orch.sync_councils()
        councils = db_session.execute(select(Council)).scalars().all()
        assert len(councils) == 2

    def test_check_health_disables_after_failures(self, db_session):
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        orch.sync_councils()
        council = db_session.execute(
            select(Council).where(Council.authority_code == "hart")
        ).scalar_one()
        for _ in range(3):
            run = ScrapeRun(council_id=council.id, status="failed", error_message="Connection refused")
            db_session.add(run)
        db_session.commit()
        disabled = orch.check_health()
        assert "hart" in disabled
        db_session.refresh(council)
        assert council.enabled is False

    def test_check_health_keeps_healthy_enabled(self, db_session):
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        orch.sync_councils()
        council = db_session.execute(
            select(Council).where(Council.authority_code == "hart")
        ).scalar_one()
        for status in ["failed", "failed", "success"]:
            run = ScrapeRun(council_id=council.id, status=status)
            db_session.add(run)
        db_session.commit()
        disabled = orch.check_health()
        assert "hart" not in disabled
        db_session.refresh(council)
        assert council.enabled is True

    def test_get_enabled_configs(self, db_session):
        orch = Orchestrator(configs=CONFIGS, session=db_session)
        orch.sync_councils()
        council = db_session.execute(
            select(Council).where(Council.authority_code == "hart")
        ).scalar_one()
        council.enabled = False
        db_session.commit()
        enabled = orch.get_enabled_configs()
        codes = {c.authority_code for c in enabled}
        assert "hart" not in codes
        assert "belfast" in codes
