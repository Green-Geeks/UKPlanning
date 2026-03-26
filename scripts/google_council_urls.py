#!/usr/bin/env python3
"""Find planning portal URLs by searching for each disabled council.

For each disabled council, searches Google for their planning portal,
extracts candidate URLs, and tests if they're Idox-compatible.

This script is meant to be run manually with results reviewed before applying.
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import yaml

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"


def get_disabled():
    disabled = {}
    for f in sorted(CONFIG_DIR.glob("*.yml")):
        data = yaml.safe_load(f.read_text())
        if data.get("enabled") == False:
            disabled[data["authority_code"]] = data
    return disabled


async def check_idox(client, url):
    """Check if a URL is Idox."""
    for suffix in ["/search.do?action=advanced", "/online-applications/search.do?action=advanced"]:
        test_url = url.rstrip("/") + suffix
        try:
            resp = await client.get(test_url, follow_redirects=True, timeout=10)
            if resp.status_code == 200 and ("advancedSearchForm" in resp.text or "searchCriteriaForm" in resp.text):
                return str(resp.url).split("/search.do")[0]
        except Exception:
            pass
    return None


async def check_alive(client, url):
    """Check if URL is alive and what it looks like."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=10)
        if resp.status_code < 400:
            final_url = str(resp.url)
            # Check for common planning portal indicators
            text = resp.text.lower()
            indicators = {
                "idox": "advancedsearchform" in text or "searchcriteriaform" in text,
                "planning_search": "planning" in text and ("search" in text or "application" in text),
                "has_form": "<form" in text,
            }
            return {"alive": True, "url": final_url, "status": resp.status_code, **indicators}
    except Exception:
        pass
    return {"alive": False}


async def apply_fixes():
    """Apply discovered URLs from the report."""
    report_path = Path(__file__).parent.parent / "google_discovery_report.json"
    with open(report_path) as f:
        report = json.load(f)

    count = 0
    for item in report.get("found", []):
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
        print("This script is driven by the Claude session using WebSearch.", flush=True)
        print("Run with 'apply' to apply results from google_discovery_report.json", flush=True)
