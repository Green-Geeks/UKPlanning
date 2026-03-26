import pytest
from pathlib import Path
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
