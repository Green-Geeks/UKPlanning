import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from migrate_configs import (
    load_scraper_list, extract_search_urls, map_platform,
    extract_base_url, generate_yaml, run_migration,
)


class TestMigrationHelpers:
    def test_extract_base_url_idox(self):
        url = "https://pa.hart.gov.uk/online-applications/search.do?action=advanced"
        assert extract_base_url(url) == "https://pa.hart.gov.uk/online-applications"

    def test_extract_base_url_pe(self):
        url = "https://eplanning.birmingham.gov.uk/Northgate/PlanningExplorer/GeneralSearch.aspx"
        assert extract_base_url(url) == "https://eplanning.birmingham.gov.uk/Northgate/PlanningExplorer"

    def test_extract_base_url_swiftlg(self):
        url = "https://www5.dudley.gov.uk/swiftlg/apas/run/wphappcriteria.display"
        assert extract_base_url(url) == "https://www5.dudley.gov.uk/swiftlg/apas/run"

    def test_map_platform_idox(self):
        assert map_platform("Idox", "scrapers.dates.idox2") == "idox"

    def test_map_platform_idox_ni(self):
        assert map_platform("IdoxNI", "scrapers.dates.idoxni") == "idox_ni"

    def test_map_platform_idox_endexc(self):
        assert map_platform("Idox", "scrapers.dates.idoxendexc") == "idox_endexc"

    def test_map_platform_idox_crumb(self):
        assert map_platform("Idox", "scrapers.dates.idoxcrumb") == "idox_crumb"

    def test_map_platform_pe(self):
        assert map_platform("PlanningExplorer", "scrapers.dates.planningexplorer") == "planning_explorer"

    def test_map_platform_swiftlg(self):
        assert map_platform("SwiftLG", "scrapers.dates.swiftlg") == "swiftlg"

    def test_map_platform_unsupported(self):
        assert map_platform("Civica", "scrapers.dates.civica") == "unsupported"

    def test_generate_yaml_basic(self):
        council = {"scraper": "Hart", "disabled": "False", "comment": ""}
        yaml = generate_yaml(council, "https://pa.hart.gov.uk/online-applications/search.do?action=advanced", "idox")
        assert "name: Hart" in yaml
        assert "authority_code: hart" in yaml
        assert "platform: idox" in yaml
        assert "pa.hart.gov.uk/online-applications" in yaml

    def test_generate_yaml_disabled(self):
        council = {"scraper": "Alderney", "disabled": "True", "comment": "No scraper"}
        yaml = generate_yaml(council, "", "unsupported")
        assert "enabled: false" in yaml


class TestFullMigration:
    def test_run_migration(self, tmp_path):
        repo_root = Path(__file__).parent.parent
        csv_path = repo_root / "scraper_list.csv"
        scrapers_dir = repo_root / "ukplanning" / "scrapers"
        if not csv_path.exists():
            pytest.skip("scraper_list.csv not found")
        output_dir = tmp_path / "councils"
        stats = run_migration(csv_path, scrapers_dir, output_dir)
        assert stats["total"] >= 400
        assert stats["with_url"] >= 300
        yml_files = list(output_dir.glob("*.yml"))
        assert len(yml_files) >= 400
