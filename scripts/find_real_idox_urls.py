#!/usr/bin/env python3
"""Find the real Idox URLs for councils with bad/guessed URLs.

Strategy: For each council, web search for their planning search page,
extract all links, and test each for Idox markers.
Uses DuckDuckGo HTML search to find the real URLs.
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, quote_plus

import httpx
import yaml
from bs4 import BeautifulSoup

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"
REPORT_PATH = Path(__file__).parent.parent / "real_idox_report.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Human-readable names for search
SEARCH_NAMES = {
    "allerdale": "Cumberland Council",
    "copeland": "Cumberland Council",
    "barrow": "Westmorland and Furness Council",
    "eden": "Westmorland and Furness Council",
    "southlakeland": "Westmorland and Furness Council",
    "daventry": "West Northamptonshire Council",
    "northampton": "West Northamptonshire Council",
    "southnorthamptonshire": "West Northamptonshire Council",
    "christchurch": "BCP Council Bournemouth Christchurch Poole",
    "poole": "BCP Council Bournemouth Christchurch Poole",
    "bournemouth": "BCP Council Bournemouth Christchurch Poole",
    "eastdorset": "Dorset Council",
    "northdorset": "Dorset Council",
    "purbeck": "Dorset Council",
    "westdorset": "Dorset Council",
    "weymouth": "Dorset Council",
    "tauntondeane": "Somerset Council",
    "westsomerset": "Somerset Council",
    "sedgemoor": "Somerset Council",
    "shepway": "Folkestone Hythe Council",
    "eastbourne": "Lewes Eastbourne Council",
    "lewes": "Lewes Eastbourne Council",
    "whitehorse": "Vale of White Horse Council",
}


def get_disabled_by_platform(platform):
    result = {}
    for f in sorted(CONFIG_DIR.glob("*.yml")):
        data = yaml.safe_load(f.read_text())
        if data.get("enabled") is False and data.get("platform") == platform:
            result[data["authority_code"]] = data
    return result


def get_search_name(code, data):
    if code in SEARCH_NAMES:
        return SEARCH_NAMES[code]
    name = data.get("name", code)
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', name)


async def search_duckduckgo(client, query):
    """Search DuckDuckGo and extract result URLs."""
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        resp = await client.get(url, follow_redirects=True, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            urls = []
            for a in soup.select("a.result__a"):
                href = a.get("href", "")
                if href.startswith("http"):
                    urls.append(href)
            # Also extract from snippets
            for a in soup.select("a.result__url"):
                href = a.get("href", "")
                if href.startswith("http"):
                    urls.append(href)
            return urls
    except Exception:
        pass
    return []


async def check_idox(client, url):
    """Check if a URL is an Idox portal. Returns the base URL if so."""
    for path in ["/online-applications/search.do?action=advanced",
                 "/search.do?action=advanced"]:
        test_url = url.rstrip("/") + path
        try:
            resp = await client.get(test_url, follow_redirects=True, timeout=12)
            if resp.status_code == 200 and ("advancedSearchForm" in resp.text or "searchCriteriaForm" in resp.text):
                final = str(resp.url).split("/search.do")[0]
                return final
        except Exception:
            pass
    return None


async def find_idox_for_council(client, code, data, sem):
    """Find the real Idox URL for a council via web search."""
    async with sem:
        name = get_search_name(code, data)
        query = f"{name} planning applications online search"

        search_results = await search_duckduckgo(client, query)

        # Extract potential Idox domains from search results
        candidate_domains = set()
        for url in search_results[:10]:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            # Add the host and potential subdomains
            candidate_domains.add(host)
            parts = host.split(".")
            if len(parts) >= 2:
                base = ".".join(parts[-2:])
                if base == "gov.uk" and len(parts) >= 3:
                    base = ".".join(parts[-3:])
                candidate_domains.add(base)

        # Generate Idox candidate URLs from discovered domains
        candidates = []
        for domain in candidate_domains:
            if not domain:
                continue
            for prefix in ["publicaccess", "planning", "pa", "planningpa",
                           "planapp", "plan", "idoxpa", "eplanning",
                           "eforms", "apps", "development", "planningrecords",
                           "searchapplications", "emaps", "portal",
                           "planningpublicaccess", "publicaccess2", "publicaccess3",
                           "pa2", "pa3"]:
                candidates.append(f"https://{prefix}.{domain}/online-applications")
            candidates.append(f"https://www.{domain}/online-applications")
            candidates.append(f"https://{domain}/online-applications")
            # Also try the search result URLs directly
            for url in search_results[:5]:
                if domain in url:
                    candidates.append(url.split("?")[0].rstrip("/"))

        # Also try Welsh Idox Cloud pattern
        clean = name.lower().replace(" ", "").replace("council", "").replace("'", "")
        candidates.append(f"https://www.{clean}idoxcloud.wales/online-applications")

        # Deduplicate
        candidates = list(dict.fromkeys(candidates))

        # Test candidates
        for candidate in candidates[:30]:
            result = await check_idox(client, candidate)
            if result:
                return {"authority_code": code, "name": data["name"], "url": result, "source": "search"}

        await asyncio.sleep(1)  # Rate limit DDG
        return None


async def main():
    idox_councils = get_disabled_by_platform("idox")
    print(f"Idox councils with bad URLs: {len(idox_councils)}")

    results = {"found": [], "not_found": []}
    sem = asyncio.Semaphore(3)

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        tasks = []
        codes = []
        for code, data in sorted(idox_councils.items()):
            tasks.append(find_idox_for_council(client, code, data, sem))
            codes.append(code)

        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for code, result in zip(codes, task_results):
            if isinstance(result, Exception):
                print(f"  {code}: ERROR - {result}")
                results["not_found"].append(code)
            elif result:
                print(f"  {code}: FOUND -> {result['url']}")
                results["found"].append(result)
            else:
                print(f"  {code}: NOT FOUND")
                results["not_found"].append(code)

    print(f"\n{'='*60}")
    print(f"Found: {len(results['found'])}")
    print(f"Not found: {len(results['not_found'])}")

    with open(REPORT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Report: {REPORT_PATH}")


def apply():
    with open(REPORT_PATH) as f:
        report = json.load(f)

    count = 0
    for item in report["found"]:
        code = item["authority_code"]
        config_path = CONFIG_DIR / f"{code}.yml"
        if not config_path.exists():
            continue
        data = yaml.safe_load(config_path.read_text())
        data["base_url"] = item["url"]
        data["platform"] = "idox"
        data["enabled"] = True
        config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        count += 1
        print(f"  {code}: {item['url']}")
    print(f"\nUpdated {count} configs")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        apply()
    else:
        asyncio.run(main())
