#!/usr/bin/env python3
"""Extract council configs from old UKPlanning codebase into YAML files."""
import csv
import re
from pathlib import Path

PLATFORM_MAP = {
    "Idox": "idox",
    "IdoxNI": "idox_ni",
    "IdoxReq": "idox",
    "PlanningExplorer": "planning_explorer",
    "SwiftLG": "swiftlg",
    "None": None,
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

SEARCH_URL_RE = re.compile(r"_search_url\s*=\s*['\"]([^'\"]+)['\"]")


def load_scraper_list(csv_path):
    rows = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def extract_search_urls(scrapers_dir):
    urls = {}
    for py_file in scrapers_dir.rglob("*.py"):
        content = py_file.read_text(errors="ignore")
        classes = re.split(r'\nclass\s+', content)
        for cls_block in classes[1:]:
            class_name_match = re.match(r'(\w+)', cls_block)
            if not class_name_match:
                continue
            class_name = class_name_match.group(1)
            url_match = SEARCH_URL_RE.search(cls_block)
            if url_match:
                urls[class_name] = url_match.group(1)
    return urls


def map_platform(scraper_type, module_name):
    if "idoxni" in module_name:
        return "idox_ni"
    if "idoxendexc" in module_name:
        return "idox_endexc"
    if "idoxcrumb" in module_name:
        return "idox_crumb"
    if "idoxscots" in module_name:
        return "idox"
    if "idox2" in module_name:
        return "idox"
    if "idoxreq" in module_name:
        return "idox"
    if "idox" in module_name and "idoxni" not in module_name:
        return "idox"
    if "swiftlg" in module_name:
        return "swiftlg"
    if "planningexplorer" in module_name:
        return "planning_explorer"
    return PLATFORM_MAP.get(scraper_type, "unsupported")


def extract_base_url(search_url):
    if not search_url:
        return ""
    url = search_url.split("?")[0]
    suffixes = [
        "/search.do", "/GeneralSearch.aspx", "/generalsearch.aspx",
        "/wphappcriteria.display", "/advancedsearch.aspx",
        "/Wphappcriteria.display",
    ]
    for suffix in suffixes:
        lower_url = url.lower()
        lower_suffix = suffix.lower()
        if lower_suffix in lower_url:
            idx = lower_url.index(lower_suffix)
            return url[:idx]
    return url.rsplit("/", 1)[0] if "/" in url else url


def generate_yaml(council, search_url, platform):
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
        'schedule: "0 3 * * *"',
        "requires_js: false",
    ]
    if disabled or platform == "unsupported" or not base_url:
        lines.append("enabled: false")
    if comment:
        lines.append(f"# {comment}")
    return "\n".join(lines) + "\n"


def run_migration(csv_path, scrapers_dir, output_dir):
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
    for f in output_dir.glob("*.yml"):
        f.unlink()
    stats = run_migration(csv_path, scrapers_dir, output_dir)
    print(f"Migration complete:")
    print(f"  Total councils: {stats['total']}")
    print(f"  With URL found: {stats['with_url']}")
    print(f"  Supported platform: {stats['supported']}")
    print(f"  Unsupported/no URL: {stats['unsupported']}")
    print(f"  Disabled: {stats['disabled']}")
