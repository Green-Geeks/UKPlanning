#!/usr/bin/env python3
"""Verify unverified URLs with longer timeouts, then apply all to configs.

Reads websearch_discovery_report.json, retries unverified URLs,
then updates all council configs with found URLs.
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import yaml

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"
REPORT_PATH = Path(__file__).parent.parent / "websearch_discovery_report.json"
FINAL_REPORT = Path(__file__).parent.parent / "final_discovery_report.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# URLs that look like standard Idox pattern - apply as idox even if verification timed out
IDOX_PATTERNS = ["/online-applications", "idoxcloud"]


async def check_idox(client, url):
    search_url = url.rstrip("/") + "/search.do?action=advanced"
    try:
        resp = await client.get(search_url, follow_redirects=True, timeout=20)
        if resp.status_code == 200 and ("advancedSearchForm" in resp.text or "searchCriteriaForm" in resp.text):
            return str(resp.url).split("/search.do")[0]
    except Exception:
        pass
    return None


async def verify_batch(client, items, sem):
    """Verify a batch of URLs."""
    results = []
    for item in items:
        async with sem:
            code = item["authority_code"]
            url = item.get("candidate_url", item.get("url", ""))
            if not url:
                results.append((code, None))
                continue

            # Try Idox check
            idox_url = await check_idox(client, url)
            if idox_url:
                results.append((code, {"platform": "idox", "url": idox_url}))
                print(f"  {code}: IDOX -> {idox_url}")
                continue

            # Check if it looks like Idox pattern
            is_idox_pattern = any(p in url for p in IDOX_PATTERNS)
            if is_idox_pattern:
                # Trust the URL even without verification
                clean_url = url.split("/search.do")[0].split("?")[0].rstrip("/")
                if "/online-applications" in clean_url:
                    clean_url = clean_url.split("/online-applications")[0] + "/online-applications"
                results.append((code, {"platform": "idox", "url": clean_url}))
                print(f"  {code}: IDOX (pattern) -> {clean_url}")
                continue

            # Try as PE
            try:
                resp = await client.get(url, follow_redirects=True, timeout=15)
                if resp.status_code < 400:
                    text = resp.text.lower()
                    final = str(resp.url)
                    if "planningexplorer" in text or "generalsearch" in text:
                        base = final.split("/Northgate")[0] if "/Northgate" in final else final.split("/PlanningExplorer")[0] if "/PlanningExplorer" in final else url
                        results.append((code, {"platform": "planning_explorer", "url": base}))
                        print(f"  {code}: PE -> {base}")
                        continue
                    if "swift" in text or "wphappcriteria" in text:
                        base = final.split("/swift")[0] if "/swift" in final.lower() else url
                        results.append((code, {"platform": "swiftlg", "url": base}))
                        print(f"  {code}: SwiftLG -> {base}")
                        continue
            except Exception:
                pass

            results.append((code, None))
            print(f"  {code}: FAILED")

    return results


async def main():
    with open(REPORT_PATH) as f:
        report = json.load(f)

    # Separate verified from unverified
    found = report["found"]
    not_found = report["not_found"]

    # Items with candidate URLs to retry
    to_retry = [item for item in not_found if item.get("candidate_url")]
    still_unknown = [item for item in not_found if not item.get("candidate_url")]

    print(f"Already found: {len(found)}")
    print(f"To retry (have candidate URL): {len(to_retry)}")
    print(f"No URL at all: {len(still_unknown)}")
    print()

    newly_found = []
    final_not_found = list(still_unknown)

    sem = asyncio.Semaphore(5)  # Lower concurrency for longer timeouts
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        results = await verify_batch(client, to_retry, sem)

        for code, result in results:
            item = next(i for i in to_retry if i["authority_code"] == code)
            if result:
                newly_found.append({
                    "authority_code": code,
                    "name": item["name"],
                    "platform": result["platform"],
                    "url": result["url"],
                    "source": "retry",
                })
            else:
                # For Idox-pattern URLs, trust them anyway
                candidate = item.get("candidate_url", "")
                if any(p in candidate for p in IDOX_PATTERNS):
                    clean = candidate.split("?")[0].rstrip("/")
                    if "/online-applications" in clean:
                        clean = clean.split("/online-applications")[0] + "/online-applications"
                    newly_found.append({
                        "authority_code": code,
                        "name": item["name"],
                        "platform": "idox",
                        "url": clean,
                        "source": "trusted_pattern",
                    })
                    print(f"  {code}: TRUSTED -> {clean}")
                else:
                    final_not_found.append(item)

    all_found = found + newly_found

    print(f"\n{'='*60}")
    print(f"Total found: {len(all_found)}")
    print(f"Still not found: {len(final_not_found)}")

    final = {
        "found": all_found,
        "not_found": final_not_found,
        "ni": report.get("ni", []),
        "skipped": report.get("skipped", []),
    }

    with open(FINAL_REPORT, "w") as f:
        json.dump(final, f, indent=2)
    print(f"Report saved: {FINAL_REPORT}")

    # Show not found
    if final_not_found:
        print(f"\nStill missing ({len(final_not_found)}):")
        for item in final_not_found:
            print(f"  - {item['authority_code']}: {item['name']}")


def apply():
    """Apply all found URLs to configs."""
    with open(FINAL_REPORT) as f:
        report = json.load(f)

    count = 0
    skipped = 0
    for item in report["found"]:
        code = item["authority_code"]
        new_url = item["url"]
        platform = item["platform"]
        config_path = CONFIG_DIR / f"{code}.yml"
        if not config_path.exists():
            print(f"  SKIP {code}: no config file")
            skipped += 1
            continue
        if platform == "unknown":
            print(f"  SKIP {code}: unknown platform")
            skipped += 1
            continue

        data = yaml.safe_load(config_path.read_text())
        if data.get("enabled"):
            continue  # already enabled, don't touch

        data["base_url"] = new_url
        data["platform"] = platform
        data["enabled"] = True
        # Remove old comments
        config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        count += 1
        print(f"  {code}: {platform} -> {new_url}")

    print(f"\nUpdated {count} configs (skipped {skipped})")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        apply()
    else:
        asyncio.run(main())
