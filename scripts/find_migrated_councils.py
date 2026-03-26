#!/usr/bin/env python3
"""Find disabled councils that migrated to Idox.

Checks all disabled non-Idox councils to see if they now have an Idox search page.
Also checks remaining dead Idox councils with broader URL patterns.
"""
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"


def get_all_disabled():
    """Get ALL disabled councils."""
    results = []
    for f in sorted(CONFIG_DIR.glob("*.yml")):
        data = yaml.safe_load(f.read_text())
        if data.get("enabled") == False:
            results.append(data)
    return results


def generate_idox_candidates(name, old_url):
    """Generate possible Idox URLs from council name and old URL."""
    candidates = set()

    # Extract domain parts from old URL
    if old_url:
        parsed = urlparse(old_url)
        host = parsed.hostname or ""
        domain_parts = host.split(".")
        if len(domain_parts) >= 2:
            base_domain = ".".join(domain_parts[-2:])
            # Handle .gov.uk domains
            if base_domain == "gov.uk" and len(domain_parts) >= 3:
                base_domain = ".".join(domain_parts[-3:])

            for prefix in ["publicaccess", "planning", "pa", "planningaccess",
                          "idox", "idoxpa", "eplanning", "planningonline",
                          "publicaccess2", "www"]:
                candidates.add(f"https://{prefix}.{base_domain}/online-applications")

            # Try original host with /online-applications
            candidates.add(f"https://{host}/online-applications")
            candidates.add(f"http://{host}/online-applications")

    # Clean name for URL guessing
    clean = name.lower().replace(" ", "").replace("'", "")
    for pattern in [
        f"https://publicaccess.{clean}.gov.uk/online-applications",
        f"https://planning.{clean}.gov.uk/online-applications",
        f"https://pa.{clean}.gov.uk/online-applications",
        f"https://idoxpa.{clean}.gov.uk/online-applications",
        f"https://planningonline.{clean}.gov.uk/online-applications",
    ]:
        candidates.add(pattern)

    return list(candidates)


async def check_idox_url(client, url):
    """Check if a URL is a working Idox search page."""
    search_url = url.rstrip("/") + "/search.do?action=advanced"
    try:
        resp = await client.get(search_url, follow_redirects=True, timeout=8)
        if resp.status_code == 200:
            text = resp.text
            if "advancedSearchForm" in text or "searchCriteriaForm" in text:
                final = str(resp.url).split("/search.do")[0]
                return final
    except Exception:
        pass
    return None


async def find_all():
    councils = get_all_disabled()
    print(f"Checking {len(councils)} disabled councils for Idox migration...\n", flush=True)

    results = {"found": [], "not_found": []}

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        follow_redirects=True,
    ) as client:
        for i, council in enumerate(councils):
            code = council["authority_code"]
            name = council["name"]
            old_url = council.get("base_url", "")
            old_platform = council.get("platform", "")
            label = f"[{i+1}/{len(councils)}]"

            candidates = generate_idox_candidates(name, old_url)

            found = None
            for url in candidates:
                found = await check_idox_url(client, url)
                if found:
                    break

            if found:
                print(f"{label} {code}: FOUND -> {found} (was {old_platform})", flush=True)
                results["found"].append({
                    "authority_code": code,
                    "name": name,
                    "old_platform": old_platform,
                    "old_url": old_url,
                    "new_url": found,
                    "new_platform": "idox",
                })
            else:
                print(f"{label} {code}: NOT FOUND (was {old_platform})", flush=True)
                results["not_found"].append({
                    "authority_code": code,
                    "name": name,
                    "old_platform": old_platform,
                    "old_url": old_url,
                })

    print(f"\n{'='*60}", flush=True)
    print(f"Found: {len(results['found'])}", flush=True)
    print(f"Not found: {len(results['not_found'])}", flush=True)

    # Group found by old platform
    by_platform = {}
    for item in results["found"]:
        p = item["old_platform"]
        by_platform[p] = by_platform.get(p, 0) + 1
    print(f"\nMigrated from:", flush=True)
    for p, count in sorted(by_platform.items(), key=lambda x: -x[1]):
        print(f"  {p}: {count}", flush=True)

    report_path = Path(__file__).parent.parent / "migration_discovery_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport: {report_path}", flush=True)


async def apply_fixes():
    report_path = Path(__file__).parent.parent / "migration_discovery_report.json"
    with open(report_path) as f:
        results = json.load(f)

    count = 0
    for item in results["found"]:
        code = item["authority_code"]
        new_url = item["new_url"]
        config_path = CONFIG_DIR / f"{code}.yml"

        if not config_path.exists():
            continue

        content = config_path.read_text()
        old_url = item["old_url"]

        # Update base_url
        if old_url:
            content = content.replace(f'base_url: "{old_url}"', f'base_url: "{new_url}"')
        else:
            content = content.replace('base_url: ""', f'base_url: "{new_url}"')

        # Update platform to idox
        old_platform = item["old_platform"]
        content = content.replace(f"platform: {old_platform}", "platform: idox")

        # Remove enabled: false
        lines = content.split("\n")
        lines = [l for l in lines if "enabled: false" not in l]
        content = "\n".join(lines)

        config_path.write_text(content)
        count += 1
        print(f"  Updated {code}: {old_platform} -> idox @ {new_url}", flush=True)

    print(f"\nUpdated {count} configs", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        asyncio.run(apply_fixes())
    else:
        asyncio.run(find_all())
