#!/usr/bin/env python3
"""Smart URL finder for disabled councils.

Uses multiple sources:
1. uk_planning_scraper authorities.csv (direct search URLs)
2. Common domain patterns from council names
3. Tests each URL for Idox compatibility
"""
import asyncio
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"


def normalize(name):
    return (name.lower()
            .replace(" ", "").replace("-", "").replace("'", "")
            .replace("&", "and").replace(",", "")
            .replace("district", "").replace("borough", "")
            .replace("council", "").replace("county", "")
            .replace("cityof", "").replace("of", "")
            .strip())


def load_external_urls():
    """Load URLs from external authorities.csv."""
    urls = {}
    csv_path = Path(__file__).parent.parent / "external_authorities.csv"
    if csv_path.exists():
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = normalize(row.get("authority_name", ""))
                url = row.get("url", "")
                if name and url:
                    urls[name] = url
    return urls


def get_disabled():
    disabled = {}
    for f in sorted(CONFIG_DIR.glob("*.yml")):
        data = yaml.safe_load(f.read_text())
        if data.get("enabled") == False:
            disabled[data["authority_code"]] = data
    return disabled


def generate_candidates(name, old_url, external_url=None):
    """Generate URL candidates from all sources."""
    candidates = []

    # External source URL first (highest quality)
    if external_url:
        parsed = urlparse(external_url)
        base = f"{parsed.scheme}://{parsed.hostname}"
        # Extract the path before search.do or similar
        path = parsed.path
        for suffix in ["/search.do", "/Default.aspx", "/GeneralSearch.aspx",
                       "/Servlet", "/run/", "/search"]:
            if suffix.lower() in path.lower():
                idx = path.lower().index(suffix.lower())
                candidates.append(f"{base}{path[:idx]}")
                break
        candidates.append(f"{base}/online-applications")

    # Common patterns from name
    clean = name.lower().replace(" ", "").replace("'", "")
    # Try with different domain patterns
    for domain_base in [clean, clean.replace("and", "")]:
        for prefix in ["publicaccess", "planning", "pa", "idoxpa", "eplanning",
                       "planningonline", "planningaccess"]:
            candidates.append(f"https://{prefix}.{domain_base}.gov.uk/online-applications")

    # From old URL
    if old_url:
        parsed = urlparse(old_url)
        host = parsed.hostname or ""
        candidates.append(f"https://{host}/online-applications")
        domain_parts = host.split(".")
        if len(domain_parts) >= 2:
            base_domain = ".".join(domain_parts[-2:])
            if base_domain == "gov.uk" and len(domain_parts) >= 3:
                base_domain = ".".join(domain_parts[-3:])
            for prefix in ["publicaccess", "planning", "pa", "idoxpa", "eplanning"]:
                candidates.append(f"https://{prefix}.{base_domain}/online-applications")

    return list(dict.fromkeys(candidates))  # dedupe preserving order


async def check_idox(client, url):
    search_url = url.rstrip("/") + "/search.do?action=advanced"
    try:
        resp = await client.get(search_url, follow_redirects=True, timeout=8)
        if resp.status_code == 200 and ("advancedSearchForm" in resp.text or "searchCriteriaForm" in resp.text):
            return str(resp.url).split("/search.do")[0]
    except Exception:
        pass
    return None


async def main():
    external_urls = load_external_urls()
    disabled = get_disabled()
    print(f"Disabled councils: {len(disabled)}", flush=True)
    print(f"External URLs available: {len(external_urls)}", flush=True)

    results = {"found": [], "not_found": []}

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        follow_redirects=True,
    ) as client:
        for i, (code, council) in enumerate(disabled.items()):
            label = f"[{i+1}/{len(disabled)}]"
            name = council["name"]
            old_url = council.get("base_url", "")
            norm = normalize(name)

            ext_url = external_urls.get(norm)
            candidates = generate_candidates(name, old_url, ext_url)

            found = None
            for url in candidates[:12]:  # limit candidates to avoid timeouts
                found = await check_idox(client, url)
                if found:
                    break

            if found:
                print(f"{label} {code}: FOUND -> {found}", flush=True)
                results["found"].append({
                    "authority_code": code,
                    "name": name,
                    "old_platform": council.get("platform", ""),
                    "old_url": old_url,
                    "new_url": found,
                })
            else:
                print(f"{label} {code}: NOT FOUND", flush=True)
                results["not_found"].append({
                    "authority_code": code,
                    "name": name,
                    "old_platform": council.get("platform", ""),
                })

    print(f"\n{'='*60}", flush=True)
    print(f"Found: {len(results['found'])}", flush=True)
    print(f"Not found: {len(results['not_found'])}", flush=True)

    report_path = Path(__file__).parent.parent / "smart_discovery_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Report: {report_path}", flush=True)


async def apply_fixes():
    report_path = Path(__file__).parent.parent / "smart_discovery_report.json"
    with open(report_path) as f:
        report = json.load(f)

    count = 0
    for item in report["found"]:
        code = item["authority_code"]
        new_url = item["new_url"]
        config_path = CONFIG_DIR / f"{code}.yml"
        if not config_path.exists():
            continue
        content = config_path.read_text()
        old_url = item.get("old_url", "")
        if old_url:
            content = content.replace(f'base_url: "{old_url}"', f'base_url: "{new_url}"')
        else:
            content = content.replace('base_url: ""', f'base_url: "{new_url}"')
        old_platform = item.get("old_platform", "")
        if old_platform:
            content = content.replace(f"platform: {old_platform}", "platform: idox")
        lines = [l for l in content.split("\n") if "enabled: false" not in l]
        content = "\n".join(lines)
        config_path.write_text(content)
        count += 1
        print(f"  Updated {code}: {new_url}", flush=True)
    print(f"\nUpdated {count} configs", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        asyncio.run(apply_fixes())
    else:
        asyncio.run(main())
