import pytest
import tempfile
import os
from pathlib import Path
from src.core.config import CouncilConfig, load_council_config, load_all_councils


SAMPLE_YAML = """
name: Hart
authority_code: hart
platform: idox
base_url: "https://publicaccess.hart.gov.uk/online-applications"
schedule: "0 3 * * *"
requires_js: false
selectors:
  reference: "th:-soup-contains('Reference') + td"
  address: "th:-soup-contains('Address') + td"
fields:
  date_received: date_validated
"""

SAMPLE_CUSTOM_YAML = """
name: Ashfield
authority_code: ashfield
platform: custom
scraper_class: "custom.ashfield.AshfieldScraper"
base_url: "https://www.ashfield.gov.uk/planning"
schedule: "0 3 * * 1"
requires_js: false
"""

SAMPLE_MINIMAL_YAML = """
name: Bexley
authority_code: bexley
platform: idox
base_url: "https://pa.bexley.gov.uk/online-applications"
"""


class TestCouncilConfig:
    def test_load_full_config(self, tmp_path):
        config_file = tmp_path / "hart.yml"
        config_file.write_text(SAMPLE_YAML)
        config = load_council_config(config_file)
        assert config.name == "Hart"
        assert config.authority_code == "hart"
        assert config.platform == "idox"
        assert config.base_url == "https://publicaccess.hart.gov.uk/online-applications"
        assert config.schedule == "0 3 * * *"
        assert config.requires_js is False
        assert config.selectors["reference"] == "th:-soup-contains('Reference') + td"
        assert config.fields["date_received"] == "date_validated"

    def test_load_custom_config(self, tmp_path):
        config_file = tmp_path / "ashfield.yml"
        config_file.write_text(SAMPLE_CUSTOM_YAML)
        config = load_council_config(config_file)
        assert config.platform == "custom"
        assert config.scraper_class == "custom.ashfield.AshfieldScraper"

    def test_load_minimal_config_defaults(self, tmp_path):
        config_file = tmp_path / "bexley.yml"
        config_file.write_text(SAMPLE_MINIMAL_YAML)
        config = load_council_config(config_file)
        assert config.schedule == "0 3 * * *"
        assert config.requires_js is False
        assert config.selectors == {}
        assert config.fields == {}
        assert config.scraper_class is None

    def test_load_all_councils(self, tmp_path):
        (tmp_path / "hart.yml").write_text(SAMPLE_YAML)
        (tmp_path / "ashfield.yml").write_text(SAMPLE_CUSTOM_YAML)
        (tmp_path / "not_yaml.txt").write_text("ignore me")
        configs = load_all_councils(tmp_path)
        assert len(configs) == 2
        codes = {c.authority_code for c in configs}
        assert codes == {"hart", "ashfield"}

    def test_invalid_config_raises(self, tmp_path):
        config_file = tmp_path / "bad.yml"
        config_file.write_text("name: Bad\n")  # missing required fields
        with pytest.raises(Exception):
            load_council_config(config_file)

    def test_duplicate_authority_code_detected(self, tmp_path):
        (tmp_path / "hart1.yml").write_text(SAMPLE_YAML)
        (tmp_path / "hart2.yml").write_text(SAMPLE_YAML)
        with pytest.raises(ValueError, match="Duplicate authority_code"):
            load_all_councils(tmp_path)
