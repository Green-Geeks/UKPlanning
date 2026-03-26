#!/usr/bin/env python3
"""Fetch planning portal URLs from PlanIt API and cross-reference with our disabled councils.

PlanIt API: https://www.planit.org.uk/api/areas/json
Returns ~417 authorities with planning_url field.
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import yaml

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"


def normalize_name(name):
    """Normalize council name for matching."""
    return (name.lower()
            .replace(" ", "")
            .replace("-", "")
            .replace("'", "")
            .replace("&", "and")
            .replace(",", "")
            .replace("district", "")
            .replace("borough", "")
            .replace("council", "")
            .replace("city", "")
            .replace("county", "")
            .replace("of", "")
            .strip())


async def fetch_planit_data():
    """Fetch all authorities from PlanIt API."""
    print("Fetching PlanIt API data...", flush=True)
    async with httpx.AsyncClient(timeout=30) as client:
        all_areas = []
        page = 1
        while True:
            resp = await client.get(
                "https://www.planit.org.uk/api/areas/json",
                params={"pg_sz": 100, "pg": page},
            )
            if resp.status_code != 200:
                print(f"API error: {resp.status_code}", flush=True)
                break
            data = resp.json()
            records = data.get("records", [])
            if not records:
                break
            all_areas.extend(records)
            print(f"  Page {page}: {len(records)} records (total: {len(all_areas)})", flush=True)
            page += 1

    print(f"\nFetched {len(all_areas)} authorities from PlanIt\n", flush=True)
    return all_areas


def get_disabled_councils():
    """Get all disabled councils."""
    disabled = {}
    for f in sorted(CONFIG_DIR.glob("*.yml")):
        data = yaml.safe_load(f.read_text())
        if data.get("enabled") == False:
            disabled[data["authority_code"]] = data
    return disabled


def match_councils(planit_areas, disabled):
    """Match PlanIt areas to our disabled councils."""
    # Build lookup from normalized names
    planit_by_name = {}
    for area in planit_areas:
        name = area.get("name", "")
        url = area.get("planning_url", "")
        if name and url:
            norm = normalize_name(name)
            planit_by_name[norm] = {"name": name, "url": url, "area": area}

    matches = []
    unmatched_disabled = []

    for code, council in disabled.items():
        norm_code = normalize_name(council["name"])

        # Try exact match
        if norm_code in planit_by_name:
            match = planit_by_name[norm_code]
            matches.append({
                "authority_code": code,
                "name": council["name"],
                "old_url": council.get("base_url", ""),
                "old_platform": council.get("platform", ""),
                "planit_name": match["name"],
                "planit_url": match["url"],
            })
        else:
            # Try fuzzy match - check if our name is contained in planit name or vice versa
            found = False
            for pnorm, pdata in planit_by_name.items():
                if norm_code in pnorm or pnorm in norm_code:
                    matches.append({
                        "authority_code": code,
                        "name": council["name"],
                        "old_url": council.get("base_url", ""),
                        "old_platform": council.get("platform", ""),
                        "planit_name": pdata["name"],
                        "planit_url": pdata["url"],
                    })
                    found = True
                    break
            if not found:
                unmatched_disabled.append(council)

    return matches, unmatched_disabled


async def check_if_idox(client, url):
    """Check if a URL leads to an Idox planning portal."""
    try:
        # Try adding /search.do?action=advanced
        for suffix in ["/search.do?action=advanced", "/online-applications/search.do?action=advanced"]:
            test_url = url.rstrip("/") + suffix
            resp = await client.get(test_url, follow_redirects=True, timeout=10)
            if resp.status_code == 200 and ("advancedSearchForm" in resp.text or "searchCriteriaForm" in resp.text):
                return str(resp.url).split("/search.do")[0]
        # Try the URL directly
        resp = await client.get(url, follow_redirects=True, timeout=10)
        if resp.status_code == 200 and ("advancedSearchForm" in resp.text or "searchCriteriaForm" in resp.text):
            return str(resp.url).split("/search.do")[0]
    except Exception:
        pass
    return None


async def main():
    planit_areas = await fetch_planit_data()
    disabled = get_disabled_councils()
    print(f"Disabled councils: {len(disabled)}", flush=True)

    matches, unmatched = match_councils(planit_areas, disabled)
    print(f"Matched to PlanIt: {len(matches)}", flush=True)
    print(f"No PlanIt match: {len(unmatched)}", flush=True)

    # Check matched URLs for Idox
    print(f"\nChecking {len(matches)} matched URLs for Idox...\n", flush=True)
    results = {"idox_found": [], "non_idox": [], "dead": []}

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0"},
        follow_redirects=True,
    ) as client:
        for i, match in enumerate(matches):
            label = f"[{i+1}/{len(matches)}]"
            url = match["planit_url"]

            idox_url = await check_if_idox(client, url)
            if idox_url:
                print(f"{label} {match['authority_code']}: IDOX -> {idox_url}", flush=True)
                match["idox_url"] = idox_url
                results["idox_found"].append(match)
            else:
                # Check if URL is at least alive
                try:
                    resp = await client.get(url, follow_redirects=True, timeout=10)
                    if resp.status_code < 400:
                        print(f"{label} {match['authority_code']}: ALIVE but not Idox -> {url}", flush=True)
                        results["non_idox"].append(match)
                    else:
                        print(f"{label} {match['authority_code']}: DEAD ({resp.status_code})", flush=True)
                        results["dead"].append(match)
                except Exception:
                    print(f"{label} {match['authority_code']}: DEAD (timeout)", flush=True)
                    results["dead"].append(match)

    print(f"\n{'='*60}", flush=True)
    print(f"Idox found: {len(results['idox_found'])}", flush=True)
    print(f"Alive but not Idox: {len(results['non_idox'])}", flush=True)
    print(f"Dead URLs: {len(results['dead'])}", flush=True)
    print(f"No PlanIt match: {len(unmatched)}", flush=True)

    # Save report
    report = {
        "idox_found": results["idox_found"],
        "non_idox": results["non_idox"],
        "dead": results["dead"],
        "unmatched": [{"authority_code": u["authority_code"], "name": u["name"]} for u in unmatched],
    }
    report_path = Path(__file__).parent.parent / "planit_discovery_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport: {report_path}", flush=True)


async def apply_fixes():
    """Apply Idox discoveries from PlanIt report."""
    report_path = Path(__file__).parent.parent / "planit_discovery_report.json"
    with open(report_path) as f:
        report = json.load(f)

    count = 0
    for item in report["idox_found"]:
        code = item["authority_code"]
        new_url = item["idox_url"]
        config_path = CONFIG_DIR / f"{code}.yml"
        if not config_path.exists():
            continue

        content = config_path.read_text()
        old_url = item.get("old_url", "")
        if old_url:
            content = content.replace(f'base_url: "{old_url}"', f'base_url: "{new_url}"')
        else:
            content = content.replace('base_url: ""', f'base_url: "{new_url}"')
        content = content.replace(f"platform: {item['old_platform']}", "platform: idox")
        lines = content.split("\n")
        lines = [l for l in lines if "enabled: false" not in l]
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
