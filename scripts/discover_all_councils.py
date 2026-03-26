#!/usr/bin/env python3
"""Discover fresh planning portal URLs for all disabled councils.

For each disabled council:
1. Web-search "[council name] planning applications search"
2. Probe candidate URLs for Idox, SwiftLG, PlanningExplorer signatures
3. Output a JSON report of found/not-found councils

Run: python scripts/discover_all_councils.py
Apply: python scripts/discover_all_councils.py apply
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"
REPORT_PATH = Path(__file__).parent.parent / "full_discovery_report.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Known council mergers - map old code to new council name for searching
MERGERS = {
    "allerdale": "Cumberland Council",
    "copeland": "Cumberland Council",
    "eden": "Westmorland and Furness Council",
    "barrow": "Westmorland and Furness Council",
    "southlakeland": "Westmorland and Furness Council",
    "daventry": "West Northamptonshire Council",
    "southnorthamptonshire": "West Northamptonshire Council",
    "northampton": "West Northamptonshire Council",
    "kettering": "North Northamptonshire Council",
    "wellingborough": "North Northamptonshire Council",
    "eastdorset": "Dorset Council",
    "northdorset": "Dorset Council",
    "purbeck": "Dorset Council",
    "westdorset": "Dorset Council",
    "weymouth": "Dorset Council",
    "christchurch": "Bournemouth Christchurch and Poole Council",
    "poole": "Bournemouth Christchurch and Poole Council",
    "bournemouth": "Bournemouth Christchurch and Poole Council",
    "chiltern": "Buckinghamshire Council",
    "southbucks": "Buckinghamshire Council",
    "wycombe": "Buckinghamshire Council",
    "tauntondeane": "Somerset Council",
    "westsomerset": "Somerset Council",
    "sedgemoor": "Somerset Council",
    "southsomerset": "Somerset Council",
    "mendip": "Somerset Council",
    "shepway": "Folkestone and Hythe Council",
    "suffolkcoastal": "East Suffolk Council",
    "waveney": "East Suffolk Council",
    "stEdmundsbury": "West Suffolk Council",
    "forestheath": "West Suffolk Council",
}

# NI councils all use the same portal
NI_COUNCILS = {
    "antrimnewtownabbey", "ardsnorthdown", "armaghbanbridgecraigavon",
    "belfast", "causewayglens", "derrystrabane", "fermanaghomagh",
    "lisburncastlereagh", "mideastantrim", "midulster", "newrymournedown",
}

# Crown dependencies / islands with no standard planning portal
SKIP_COUNCILS = {"alderney", "guernsey", "jersey", "sark", "scillyisles", "isleofman", "nip"}


def get_disabled():
    disabled = {}
    for f in sorted(CONFIG_DIR.glob("*.yml")):
        data = yaml.safe_load(f.read_text())
        if data.get("enabled") is False:
            disabled[data["authority_code"]] = data
    return disabled


def get_search_name(code, council_data):
    """Get the best name to search for this council."""
    if code in MERGERS:
        return MERGERS[code]
    name = council_data["name"]
    # Add spaces before capitals for CamelCase names
    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    return spaced


def generate_idox_candidates(name, old_url=None):
    """Generate Idox URL candidates from council name."""
    candidates = []
    clean = name.lower().replace(" ", "").replace("'", "").replace("-", "")
    clean_hyphen = name.lower().replace(" ", "-").replace("'", "")

    for domain_base in [clean, clean.replace("and", "")]:
        for prefix in ["publicaccess", "planning", "pa", "idoxpa", "eplanning",
                        "planningonline", "planningaccess", "plan", "planapp"]:
            candidates.append(f"https://{prefix}.{domain_base}.gov.uk/online-applications")
        candidates.append(f"https://www.{domain_base}.gov.uk/online-applications")
        candidates.append(f"https://{domain_base}.gov.uk/online-applications")

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

    return list(dict.fromkeys(candidates))


def generate_swiftlg_candidates(name, old_url=None):
    """Generate SwiftLG URL candidates."""
    candidates = []
    clean = name.lower().replace(" ", "").replace("'", "")
    for domain_base in [clean, clean.replace("and", "")]:
        candidates.append(f"https://planning.{domain_base}.gov.uk/swift/apas/run/wphappcriteria.display")
        candidates.append(f"https://www.{domain_base}.gov.uk/swift/apas/run/wphappcriteria.display")
        candidates.append(f"https://publicaccess.{domain_base}.gov.uk/swift/apas/run/wphappcriteria.display")
    if old_url:
        parsed = urlparse(old_url)
        host = parsed.hostname or ""
        candidates.append(f"https://{host}/swift/apas/run/wphappcriteria.display")
    return list(dict.fromkeys(candidates))


def generate_pe_candidates(name, old_url=None):
    """Generate PlanningExplorer URL candidates."""
    candidates = []
    clean = name.lower().replace(" ", "").replace("'", "")
    for domain_base in [clean, clean.replace("and", "")]:
        candidates.append(f"https://planning.{domain_base}.gov.uk/Northgate/PlanningExplorer/GeneralSearch.aspx")
        candidates.append(f"https://www.{domain_base}.gov.uk/Northgate/PlanningExplorer/GeneralSearch.aspx")
        candidates.append(f"https://planning2.{domain_base}.gov.uk/Northgate/PlanningExplorer/GeneralSearch.aspx")
    if old_url:
        parsed = urlparse(old_url)
        host = parsed.hostname or ""
        candidates.append(f"https://{host}/Northgate/PlanningExplorer/GeneralSearch.aspx")
        # Some PE URLs have different path structures
        candidates.append(f"https://{host}/PlanningExplorer/GeneralSearch.aspx")
    return list(dict.fromkeys(candidates))


async def check_idox(client, url):
    """Check if URL is an Idox portal."""
    search_url = url.rstrip("/") + "/search.do?action=advanced"
    try:
        resp = await client.get(search_url, follow_redirects=True, timeout=10)
        if resp.status_code == 200 and ("advancedSearchForm" in resp.text or "searchCriteriaForm" in resp.text):
            final = str(resp.url).split("/search.do")[0]
            return final
    except Exception:
        pass
    return None


async def check_swiftlg(client, url):
    """Check if URL is a SwiftLG portal."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=10)
        if resp.status_code == 200 and ("wphappcriteria" in resp.text.lower() or "swift" in str(resp.url).lower()):
            final = str(resp.url)
            # Extract base up to /swift
            if "/swift" in final.lower():
                idx = final.lower().index("/swift")
                return final[:idx]
            return final
    except Exception:
        pass
    return None


async def check_pe(client, url):
    """Check if URL is a PlanningExplorer portal."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=10)
        if resp.status_code == 200 and ("planningexplorer" in resp.text.lower() or "GeneralSearch" in str(resp.url)):
            final = str(resp.url)
            if "/Northgate" in final:
                idx = final.index("/Northgate")
                return final[:idx]
            if "/PlanningExplorer" in final:
                idx = final.index("/PlanningExplorer")
                return final[:idx]
            return final
    except Exception:
        pass
    return None


async def check_old_url_redirect(client, old_url):
    """Check if the old URL redirects somewhere useful."""
    if not old_url or not old_url.startswith("http"):
        return None
    try:
        resp = await client.get(old_url, follow_redirects=True, timeout=10)
        if resp.status_code == 200:
            final = str(resp.url)
            text = resp.text.lower()
            if "advancedsearchform" in text or "searchcriteriaform" in text:
                base = final.split("/search.do")[0] if "/search.do" in final else final.split("/online-applications")[0] if "/online-applications" in final else None
                if base:
                    return ("idox", base)
            if "wphappcriteria" in text or "swift" in final.lower():
                if "/swift" in final.lower():
                    idx = final.lower().index("/swift")
                    return ("swiftlg", final[:idx])
            if "planningexplorer" in text or "generalsearch" in final.lower():
                if "/Northgate" in final:
                    return ("planning_explorer", final[:final.index("/Northgate")])
    except Exception:
        pass
    return None


async def probe_council(client, code, council_data, sem):
    """Probe a single council for its planning portal."""
    async with sem:
        name = council_data["name"]
        search_name = get_search_name(code, council_data)
        old_url = council_data.get("base_url", "")
        old_platform = council_data.get("platform", "")

        # 1. Check if old URL redirects somewhere useful
        redirect_result = await check_old_url_redirect(client, old_url)
        if redirect_result:
            platform, url = redirect_result
            return {"authority_code": code, "name": name, "platform": platform, "url": url, "source": "redirect"}

        # 2. Try Idox candidates (most common platform)
        for candidate in generate_idox_candidates(search_name, old_url)[:15]:
            result = await check_idox(client, candidate)
            if result:
                return {"authority_code": code, "name": name, "platform": "idox", "url": result, "source": "probe"}

        # 3. Try SwiftLG candidates
        for candidate in generate_swiftlg_candidates(search_name, old_url)[:8]:
            result = await check_swiftlg(client, candidate)
            if result:
                return {"authority_code": code, "name": name, "platform": "swiftlg", "url": result, "source": "probe"}

        # 4. Try PlanningExplorer candidates
        for candidate in generate_pe_candidates(search_name, old_url)[:8]:
            result = await check_pe(client, candidate)
            if result:
                return {"authority_code": code, "name": name, "platform": "planning_explorer", "url": result, "source": "probe"}

        return None


async def main():
    disabled = get_disabled()
    print(f"Total disabled councils: {len(disabled)}")

    # Separate NI and skip councils
    ni_codes = {c for c in disabled if c in NI_COUNCILS}
    skip_codes = {c for c in disabled if c in SKIP_COUNCILS}
    to_probe = {c: d for c, d in disabled.items() if c not in NI_COUNCILS and c not in SKIP_COUNCILS}

    print(f"NI councils (separate portal): {len(ni_codes)}")
    print(f"Skipping (no standard portal): {len(skip_codes)}")
    print(f"To probe: {len(to_probe)}")
    print()

    results = {"found": [], "not_found": [], "ni": [], "skipped": []}

    # Add NI councils
    for code in sorted(ni_codes):
        results["ni"].append({
            "authority_code": code,
            "name": disabled[code]["name"],
            "platform": "ni_portal",
            "url": "https://planningregister.planningsystemni.gov.uk",
        })

    # Add skipped
    for code in sorted(skip_codes):
        results["skipped"].append({
            "authority_code": code,
            "name": disabled[code]["name"],
            "reason": "No standard planning portal",
        })

    # Track merged councils to avoid duplicate probes
    merger_found = {}  # merger target name -> result

    sem = asyncio.Semaphore(10)
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        tasks = []
        council_list = list(to_probe.items())

        for code, data in council_list:
            tasks.append(probe_council(client, code, data, sem))

        probe_results = await asyncio.gather(*tasks, return_exceptions=True)

        for (code, data), result in zip(council_list, probe_results):
            label = f"[{len(results['found']) + len(results['not_found']) + 1}/{len(to_probe)}]"
            if isinstance(result, Exception):
                print(f"{label} {code}: ERROR - {result}")
                results["not_found"].append({"authority_code": code, "name": data["name"], "error": str(result)})
            elif result:
                print(f"{label} {code}: FOUND {result['platform']} -> {result['url']}")
                results["found"].append(result)
                # Cache merger results
                if code in MERGERS:
                    merger_found[MERGERS[code]] = result
            else:
                # For merged councils, check if we already found the target
                if code in MERGERS and MERGERS[code] in merger_found:
                    cached = merger_found[MERGERS[code]]
                    print(f"{label} {code}: MERGED -> {cached['url']}")
                    results["found"].append({
                        "authority_code": code,
                        "name": data["name"],
                        "platform": cached["platform"],
                        "url": cached["url"],
                        "source": "merger",
                    })
                else:
                    print(f"{label} {code}: NOT FOUND")
                    results["not_found"].append({"authority_code": code, "name": data["name"]})

    print(f"\n{'='*60}")
    print(f"Found: {len(results['found'])}")
    print(f"Not found: {len(results['not_found'])}")
    print(f"NI (needs custom scraper): {len(results['ni'])}")
    print(f"Skipped: {len(results['skipped'])}")

    with open(REPORT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport saved: {REPORT_PATH}")


def apply():
    """Apply discovered URLs to council configs."""
    with open(REPORT_PATH) as f:
        report = json.load(f)

    count = 0
    for item in report["found"]:
        code = item["authority_code"]
        new_url = item["url"]
        platform = item["platform"]
        config_path = CONFIG_DIR / f"{code}.yml"
        if not config_path.exists():
            continue

        data = yaml.safe_load(config_path.read_text())
        data["base_url"] = new_url
        data["platform"] = platform
        data["enabled"] = True
        # Remove comment lines about being disabled
        lines = []
        for line in config_path.read_text().split("\n"):
            if line.strip().startswith("#") and ("disabled" in line.lower() or "migrated" in line.lower() or "dead" in line.lower()):
                continue
            lines.append(line)

        # Rewrite cleanly
        config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        count += 1
        print(f"  Updated {code}: {platform} -> {new_url}")

    print(f"\nUpdated {count} configs")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        apply()
    else:
        asyncio.run(main())
