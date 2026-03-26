from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel


class CouncilConfig(BaseModel):
    """Configuration for a single council scraper."""

    name: str
    authority_code: str
    platform: str
    base_url: str
    schedule: str = "0 3 * * *"
    requires_js: bool = False
    enabled: bool = True
    selectors: Dict[str, str] = {}
    fields: Dict[str, str] = {}
    scraper_class: Optional[str] = None
    variant: Optional[str] = None
    rate_limit_delay: float = 1.0
    batch_size_days: int = 14


def load_council_config(path: Path) -> CouncilConfig:
    """Load a single council config from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return CouncilConfig(**data)


def load_all_councils(directory: Path) -> List[CouncilConfig]:
    """Load all council configs from a directory of YAML files."""
    configs: List[CouncilConfig] = []
    seen_codes: Dict[str, Path] = {}
    for path in sorted(directory.iterdir()):
        if path.suffix not in (".yml", ".yaml"):
            continue
        config = load_council_config(path)
        if config.authority_code in seen_codes:
            raise ValueError(
                f"Duplicate authority_code '{config.authority_code}' "
                f"in {path} and {seen_codes[config.authority_code]}"
            )
        seen_codes[config.authority_code] = path
        configs.append(config)
    return configs
