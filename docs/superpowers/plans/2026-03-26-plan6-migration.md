# Plan 6: Migration — Extract Council Configs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract all ~430 council configurations from the old codebase into YAML config files, mapping each to the correct platform scraper. Then verify which URLs still respond.

**Architecture:** A one-time migration script that parses the old Python scraper files to extract `_search_url` and `_authority_name` values, maps `scraper_type` from `scraper_list.csv` to our new platform names, and generates YAML files. A separate URL verification script checks which councils are still reachable.

**Tech Stack:** Python scripts, csv, re, httpx (for URL checking)

---

## File Structure

```
scripts/
├── migrate_configs.py      # Extract configs from old codebase → YAML
└── verify_urls.py           # Check which council URLs still respond
src/
└── config/
    └── councils/            # Generated YAML files (430+)
```

---

### Task 1: Migration Script

**Files:**
- Create: `scripts/migrate_configs.py`
- Create: `tests/test_migration.py`

- [ ] **Step 1: Write the migration script**

```python
#!/usr/bin/env python3
"""Extract council configs from old UKPlanning codebase into YAML files.

Reads scraper_list.csv for the council registry, then scans old Python
scraper files to extract _search_url values. Outputs one YAML file per
council into src/config/councils/.
"""
import csv
import os
import re
import sys
from pathlib import Path

# Map old scraper_type names to our new platform names
PLATFORM_MAP = {
    "Idox": "idox",
    "IdoxNI": "idox_ni",
    "IdoxReq": "idox",  # same scraper, just used requests in old code
    "PlanningExplorer": "planning_explorer",
    "SwiftLG": "swiftlg",
    "None": None,  # NoScraper — disabled
    # Platforms we haven't built yet — map to "unsupported" for now
    "AcolNet": "unsupported",
    "AppSearchServ": "unsupported",
    "Astun": "unsupported",
    "Atrium": "unsupported",
    "Civica": "unsupported",
    "Custom": "unsupported",
    "EAccessv2": "unsupported",
    "Fastweb": "unsupported",
    "Ocella2": "unsupported",
    "PublicAccess": "unsupported",
    "Thames": "unsupported",
    "Telerik": "unsupported",
    "WAM": "unsupported",
    "AnnualList": "unsupported",
    "NIP": "unsupported",
}

# Map old scraper_type to Idox variant
IDOX_VARIANT_MAP = {
    "Idox": "idox",
}

# Regex to extract _search_url from Python source files
SEARCH_URL_RE = re.compile(r"_search_url\s*=\s*['\"]([^'\"]+)['\"]")
AUTHORITY_NAME_RE = re.compile(r"_authority_name\s*=\s*['\"]([^'\"]+)['\"]")


def load_scraper_list(csv_path: Path) -> list[dict]:
    """Load scraper_list.csv into a list of dicts."""
    rows = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def extract_search_urls(scrapers_dir: Path) -> dict[str, str]:
    """Scan old Python scraper files to extract _search_url per class."""
    urls = {}
    for py_file in scrapers_dir.rglob("*.py"):
        content = py_file.read_text(errors="ignore")
        # Find all class definitions with their _search_url and _authority_name
        classes = re.split(r'\nclass\s+', content)
        for cls_block in classes[1:]:  # skip module-level code
            class_name_match = re.match(r'(\w+)', cls_block)
            if not class_name_match:
                continue
            class_name = class_name_match.group(1)
            url_match = SEARCH_URL_RE.search(cls_block)
            if url_match:
                urls[class_name] = url_match.group(1)
    return urls


def map_platform(scraper_type: str, module_name: str) -> str:
    """Map old scraper_type to new platform name."""
    # Check for Idox variants based on module name
    if "idoxni" in module_name:
        return "idox_ni"
    if "idoxendexc" in module_name:
        return "idox_endexc"
    if "idoxcrumb" in module_name:
        return "idox_crumb"
    if "idoxscots" in module_name:
        return "idox"  # scots use standard idox now
    if "idox2" in module_name:
        return "idox"
    if "idoxreq" in module_name:
        return "idox"
    if "swiftlg" in module_name:
        return "swiftlg"
    if "planningexplorer" in module_name:
        return "planning_explorer"

    return PLATFORM_MAP.get(scraper_type, "unsupported")


def extract_base_url(search_url: str) -> str:
    """Extract base URL from full search URL.

    e.g. 'https://pa.hart.gov.uk/online-applications/search.do?action=advanced'
    -> 'https://pa.hart.gov.uk/online-applications'
    """
    if not search_url:
        return ""
    # Remove query string
    url = search_url.split("?")[0]
    # Remove known search page suffixes
    suffixes = [
        "/search.do",
        "/GeneralSearch.aspx",
        "/wphappcriteria.display",
        "/advancedsearch.aspx",
        "/Generic/StdDetails.aspx",
    ]
    for suffix in suffixes:
        if suffix.lower() in url.lower():
            idx = url.lower().index(suffix.lower())
            return url[:idx]
    # Fallback: strip last path component
    return url.rsplit("/", 1)[0]


def generate_yaml(council: dict, search_url: str, platform: str) -> str:
    """Generate YAML config string for a council."""
    name = council["scraper"]
    code = name.lower().replace(" ", "_")
    base_url = extract_base_url(search_url)
    disabled = council.get("disabled", "False") == "True"
    comment = council.get("comment", "")

    lines = [
        f"name: {name}",
        f"authority_code: {code}",
        f"platform: {platform}",
        f'base_url: "{base_url}"' if base_url else 'base_url: ""',
        f'schedule: "0 3 * * *"',
        f"requires_js: false",
    ]

    if disabled or platform == "unsupported" or not base_url:
        lines.append("enabled: false")

    if comment:
        lines.append(f"# {comment}")

    return "\n".join(lines) + "\n"


def run_migration(
    csv_path: Path,
    scrapers_dir: Path,
    output_dir: Path,
):
    """Main migration: read CSV + old code, generate YAML configs."""
    rows = load_scraper_list(csv_path)
    urls = extract_search_urls(scrapers_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    stats = {"total": 0, "with_url": 0, "supported": 0, "unsupported": 0, "disabled": 0}

    for row in rows:
        stats["total"] += 1
        class_name = row["class_name"]
        scraper_type = row["scraper_type"]
        module_name = row["module_name"]
        name = row["scraper"]
        code = name.lower().replace(" ", "_")

        search_url = urls.get(class_name, "")
        if search_url:
            stats["with_url"] += 1

        platform = map_platform(scraper_type, module_name)

        if platform == "unsupported" or not search_url:
            stats["unsupported"] += 1
        else:
            stats["supported"] += 1

        if row.get("disabled", "False") == "True":
            stats["disabled"] += 1

        yaml_content = generate_yaml(row, search_url, platform)
        output_file = output_dir / f"{code}.yml"
        output_file.write_text(yaml_content)

    return stats


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    csv_path = repo_root / "scraper_list.csv"
    scrapers_dir = repo_root / "ukplanning" / "scrapers"
    output_dir = repo_root / "src" / "config" / "councils"

    # Remove existing sample configs
    for f in output_dir.glob("*.yml"):
        f.unlink()

    stats = run_migration(csv_path, scrapers_dir, output_dir)
    print(f"Migration complete:")
    print(f"  Total councils: {stats['total']}")
    print(f"  With URL found: {stats['with_url']}")
    print(f"  Supported platform: {stats['supported']}")
    print(f"  Unsupported/no URL: {stats['unsupported']}")
    print(f"  Disabled: {stats['disabled']}")
```

- [ ] **Step 2: Write tests**

```python
# tests/test_migration.py
import pytest
from pathlib import Path

# Add scripts to path for import
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from migrate_configs import (
    load_scraper_list,
    extract_search_urls,
    map_platform,
    extract_base_url,
    generate_yaml,
    run_migration,
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
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_migration.py -v`
Expected: All 13 tests PASS

- [ ] **Step 4: Commit migration script**

```bash
git add scripts/migrate_configs.py tests/test_migration.py
git commit -m "feat: add migration script to extract council configs from old codebase"
```

---

### Task 2: Run Migration & Generate YAML Configs

**Files:**
- Modify: `src/config/councils/*.yml` (mass generate)

- [ ] **Step 1: Run the migration script**

Run: `python3 scripts/migrate_configs.py`
Expected: Output showing stats for ~430 councils

- [ ] **Step 2: Verify generated configs**

Run: `ls src/config/councils/*.yml | wc -l`
Expected: ~430 files

Run: `python3 -c "from src.core.config import load_all_councils; from pathlib import Path; configs = load_all_councils(Path('src/config/councils')); print(f'{len(configs)} configs loaded')"``
Expected: configs load without validation errors

- [ ] **Step 3: Commit generated configs**

```bash
git add src/config/councils/
git commit -m "feat: generate YAML configs for 430 UK councils from old codebase"
```

---

### Task 3: URL Verification Script

**Files:**
- Create: `scripts/verify_urls.py`

- [ ] **Step 1: Write URL verification script**

```python
#!/usr/bin/env python3
"""Check which council base URLs still respond.

Reads YAML configs and makes HEAD requests to each base_url.
Outputs a report of responsive, redirected, and dead URLs.
"""
import asyncio
import sys
from pathlib import Path

import httpx
import yaml


async def check_url(client: httpx.AsyncClient, config_path: Path) -> dict:
    """Check if a council's base URL responds."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    name = config.get("name", "")
    base_url = config.get("base_url", "")
    platform = config.get("platform", "")

    if not base_url:
        return {"name": name, "status": "no_url", "platform": platform}

    try:
        response = await client.head(base_url, follow_redirects=True, timeout=15)
        return {
            "name": name,
            "base_url": base_url,
            "status": "ok" if response.status_code < 400 else f"http_{response.status_code}",
            "status_code": response.status_code,
            "platform": platform,
            "final_url": str(response.url),
        }
    except httpx.TimeoutException:
        return {"name": name, "base_url": base_url, "status": "timeout", "platform": platform}
    except Exception as e:
        return {"name": name, "base_url": base_url, "status": "error", "error": str(e), "platform": platform}


async def verify_all(config_dir: Path, concurrency: int = 20):
    """Check all council URLs with limited concurrency."""
    configs = sorted(config_dir.glob("*.yml"))
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        headers={"User-Agent": "UKPlanningScraper/2.0 URL Check"},
    ) as client:
        async def limited_check(path):
            async with semaphore:
                return await check_url(client, path)

        results = await asyncio.gather(*[limited_check(p) for p in configs])

    # Categorize results
    ok = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] not in ("ok", "no_url")]
    no_url = [r for r in results if r["status"] == "no_url"]

    print(f"\n=== URL Verification Report ===")
    print(f"Total configs: {len(results)}")
    print(f"Responding: {len(ok)}")
    print(f"Failed: {len(failed)}")
    print(f"No URL: {len(no_url)}")

    if failed:
        print(f"\n--- Failed URLs ---")
        for r in sorted(failed, key=lambda x: x["name"]):
            print(f"  {r['name']}: {r['status']} — {r.get('base_url', '')}")

    # Write full results to file
    report_path = config_dir.parent.parent.parent / "url_report.txt"
    with open(report_path, "w") as f:
        for r in sorted(results, key=lambda x: x["name"]):
            f.write(f"{r['name']}\t{r.get('platform', '')}\t{r['status']}\t{r.get('base_url', '')}\n")
    print(f"\nFull report: {report_path}")


if __name__ == "__main__":
    config_dir = Path(__file__).parent.parent / "src" / "config" / "councils"
    asyncio.run(verify_all(config_dir))
```

- [ ] **Step 2: Commit**

```bash
git add scripts/verify_urls.py
git commit -m "feat: add URL verification script for council configs"
```

Note: Actually running verify_urls.py is optional and should be done manually when ready — it makes ~430 HTTP requests to live council websites.

---

## Summary

After completing this plan you will have:

- Migration script that extracts configs from the old codebase
- ~430 YAML config files generated (one per council)
- URL verification script ready to check which councils are still reachable
- Platform mapping showing which councils use supported vs unsupported platforms

**Coverage breakdown after migration:**
- Supported platforms (Idox, PE, SwiftLG): ~291 councils with configs ready to scrape
- Unsupported platforms: ~133 councils marked `enabled: false` (can be built incrementally)
- Disabled (no website): 6 councils

**What's next:** With all 6 plans complete, you have a fully functional scraping system. The next steps are operational:
1. Deploy to cloud server (Docker Compose)
2. Run `verify_urls.py` to find which URLs work
3. Start the scheduler — it will begin scraping all supported councils
4. Incrementally fix broken scrapers and add unsupported platforms
