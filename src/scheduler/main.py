import logging
from pathlib import Path
from sqlalchemy.orm import Session

from src.core.config import load_all_councils, CouncilConfig
from src.scheduler.orchestrator import Orchestrator
from src.scheduler.registry import ScraperRegistry

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config" / "councils"


def get_scheduler_configs(config_dir=DEFAULT_CONFIG_DIR):
    return load_all_councils(config_dir)


def load_and_sync(config_dir=DEFAULT_CONFIG_DIR, session=None, registry=None):
    configs = get_scheduler_configs(config_dir)
    if registry is None:
        registry = ScraperRegistry()
    orch = Orchestrator(configs=configs, session=session, registry=registry)
    orch.sync_councils()
    logger.info("Synced %d councils to database", len(configs))
    return orch
