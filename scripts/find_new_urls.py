#!/usr/bin/env python3
"""Find new URLs for disabled Idox councils.

Many councils just moved to HTTPS or changed subdomains.
This script tries common URL patterns to find working search pages.
"""
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"


def get_disabled_idox():
    """Get all disabled councils on Idox-like platforms."""
    results = []
    for f in sorted(CONFIG_DIR.glob("*.yml")):
        data = yaml.safe_load(f.read_text())
        if data.get("enabled") == False and data.get("platform", "").startswith("idox"):
            results.append(data)
    return results


def generate_url_candidates(base_url):
    """Generate possible new URLs from old base URL."""
    if not base_url:
        return []

    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    path = parsed.path.rstrip("/")

    candidates = set()

    # Try HTTPS version
    if parsed.scheme == "http":
        candidates.add(f"https://{host}{path}")

    # Try common Idox path patterns
    common_paths = [
        "/online-applications",
        "/publicaccess",
    ]
    for p in common_paths:
        candidates.add(f"https://{host}{p}")
        candidates.add(f"http://{host}{p}")

    # Try with/without www
    if host.startswith("www."):
        alt_host = host[4:]
    else:
        alt_host = f"www.{host}"
    candidates.add(f"https://{alt_host}{path}")
    for p in common_paths:
        candidates.add(f"https://{alt_host}{p}")

    # Try common subdomain patterns
    domain_parts = host.split(".")
    if len(domain_parts) >= 2:
        base_domain = ".".join(domain_parts[-2:])
        for prefix in ["publicaccess", "planning", "pa", "planningaccess"]:
            candidates.add(f"https://{prefix}.{base_domain}/online-applications")

    # Remove the original URL
    candidates.discard(base_url)

    return list(candidates)


async def check_idox_url(client, url):
    """Check if a URL is a working Idox search page."""
    search_url = url.rstrip("/") + "/search.do?action=advanced"
    try:
        resp = await client.get(search_url, follow_redirects=True, timeout=10)
        if resp.status_code == 200:
            text = resp.text
            if "advancedSearchForm" in text or "searchCriteriaForm" in text:
                # Extract the real base URL after redirects
                final = str(resp.url).split("/search.do")[0]
                return final
    except Exception:
        pass
    return None


async def find_urls():
    councils = get_disabled_idox()
    print(f"Checking {len(councils)} disabled Idox councils...\n")

    results = {"found": [], "not_found": []}

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        follow_redirects=True,
    ) as client:
        for i, council in enumerate(councils):
            code = council["authority_code"]
            old_url = council.get("base_url", "")
            platform = council.get("platform", "idox")
            label = f"[{i+1}/{len(councils)}]"

            # First try the old URL with HTTPS
            candidates = [old_url] + generate_url_candidates(old_url)

            found = None
            for url in candidates:
                if not url:
                    continue
                found = await check_idox_url(client, url)
                if found:
                    break

            if found:
                print(f"{label} {code}: FOUND -> {found}", flush=True)
                results["found"].append({
                    "authority_code": code,
                    "name": council["name"],
                    "platform": platform,
                    "old_url": old_url,
                    "new_url": found,
                })
            else:
                print(f"{label} {code}: NOT FOUND", flush=True)
                results["not_found"].append({
                    "authority_code": code,
                    "name": council["name"],
                    "platform": platform,
                    "old_url": old_url,
                })

    print(f"\n{'='*60}")
    print(f"Found: {len(results['found'])}")
    print(f"Not found: {len(results['not_found'])}")

    # Write report
    report_path = Path(__file__).parent.parent / "url_discovery_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport: {report_path}")

    return results


async def apply_fixes(report_path):
    """Apply discovered URLs to config files."""
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
        content = content.replace(f'base_url: "{old_url}"', f'base_url: "{new_url}"')
        # Remove enabled: false
        lines = content.split("\n")
        lines = [l for l in lines if "enabled: false" not in l]
        content = "\n".join(lines)

        config_path.write_text(content)
        count += 1
        print(f"  Updated {code}: {new_url}")

    print(f"\nUpdated {count} configs")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        report = Path(__file__).parent.parent / "url_discovery_report.json"
        asyncio.run(apply_fixes(report))
    else:
        asyncio.run(find_urls())
