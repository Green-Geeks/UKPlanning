#!/usr/bin/env python3
"""Comprehensive audit of all enabled council scrapers.

Tests both gather_ids AND fetch_detail for each council, grades data quality.

Grades:
  FULL    - gather_ids works, fetch_detail extracts all key fields
  PARTIAL - gather_ids works, fetch_detail missing some fields
  GATHER  - gather_ids works but fetch_detail fails
  FAIL    - gather_ids fails
  EMPTY   - gather_ids returns 0 results (may be valid for small councils)

Outputs: council_audit_report.json with full details
"""
import asyncio
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from src.core.config import load_all_councils
from src.scheduler.registry import ScraperRegistry

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"

KEY_FIELDS = ["reference", "address", "description"]
IMPORTANT_FIELDS = ["application_type", "status", "date_validated", "ward", "parish", "case_officer"]


async def audit_council(config, registry, date_from, date_to):
    """Full audit: gather_ids + fetch_detail for first app."""
    result = {
        "authority_code": config.authority_code,
        "name": config.name,
        "platform": config.platform,
        "base_url": config.base_url,
    }

    try:
        scraper = registry.create_scraper(config)
    except KeyError as e:
        result["grade"] = "FAIL"
        result["error"] = f"Unsupported platform: {e}"
        return result

    # Step 1: gather_ids
    try:
        ids = await scraper.gather_ids(date_from, date_to)
        result["apps_found"] = len(ids)
    except Exception as e:
        result["grade"] = "FAIL"
        result["error"] = str(e)[:300]
        await _close_client(scraper)
        return result

    if not ids:
        result["grade"] = "EMPTY"
        result["error"] = None
        await _close_client(scraper)
        return result

    # Step 2: fetch_detail for first application
    first = ids[0]
    try:
        detail = await scraper.fetch_detail(first)
    except Exception as e:
        result["grade"] = "GATHER"
        result["error"] = f"fetch_detail failed: {str(e)[:200]}"
        await _close_client(scraper)
        return result

    # Step 3: Grade data quality
    fields_present = {}
    fields_missing = []

    for field in KEY_FIELDS:
        val = getattr(detail, field, None)
        if val:
            fields_present[field] = str(val)[:100]
        else:
            fields_missing.append(field)

    important_present = []
    important_missing = []
    for field in IMPORTANT_FIELDS:
        val = getattr(detail, field, None)
        if val:
            important_present.append(field)
            fields_present[field] = str(val)[:100]
        else:
            important_missing.append(field)

    result["sample_app"] = {
        "uid": first.uid,
        "fields_present": fields_present,
        "key_missing": fields_missing,
        "important_missing": important_missing,
    }

    if fields_missing:
        result["grade"] = "PARTIAL"
        result["error"] = f"Missing key fields: {', '.join(fields_missing)}"
    elif len(important_missing) > 3:
        result["grade"] = "PARTIAL"
        result["error"] = f"Missing {len(important_missing)} important fields: {', '.join(important_missing)}"
    else:
        result["grade"] = "FULL"
        result["error"] = None

    await _close_client(scraper)
    return result


async def _close_client(scraper):
    if hasattr(scraper, "_client") and hasattr(scraper._client, "_client"):
        try:
            await scraper._client._client.aclose()
        except Exception:
            pass


async def run_audit():
    configs = load_all_councils(CONFIG_DIR)
    registry = ScraperRegistry()

    enabled = [c for c in configs if c.enabled and c.platform in registry.list_platforms()]
    print(f"Auditing {len(enabled)} enabled councils with supported platforms\n")

    date_to = date.today()
    date_from = date_to - timedelta(days=14)

    results = []
    grades = {"FULL": 0, "PARTIAL": 0, "GATHER": 0, "EMPTY": 0, "FAIL": 0}

    for i, config in enumerate(enabled):
        label = f"[{i+1}/{len(enabled)}]"
        sys.stdout.write(f"\r{label} Auditing {config.name}...                         ")
        sys.stdout.flush()

        result = await audit_council(config, registry, date_from, date_to)
        results.append(result)
        grade = result["grade"]
        grades[grade] += 1

        symbol = {"FULL": "+", "PARTIAL": "~", "GATHER": "G", "EMPTY": "0", "FAIL": "X"}[grade]
        apps = result.get("apps_found", 0)
        error = result.get("error", "")
        sys.stdout.write(f"\r{label} [{symbol}] {config.name}: {grade} ({apps} apps)")
        if error:
            sys.stdout.write(f" — {error[:60]}")
        sys.stdout.write("\n")

    # Summary
    print(f"\n{'='*60}")
    print(f"AUDIT RESULTS")
    print(f"{'='*60}")
    for grade, count in grades.items():
        bar = "#" * count
        print(f"  {grade:8s}: {count:3d} {bar}")
    print(f"  {'TOTAL':8s}: {len(results)}")

    # Group issues
    partial = [r for r in results if r["grade"] == "PARTIAL"]
    if partial:
        print(f"\n--- Partial ({len(partial)}) ---")
        for r in partial:
            missing = r["sample_app"]["key_missing"] + r["sample_app"]["important_missing"]
            print(f"  {r['name']}: missing {', '.join(missing)}")

    failed = [r for r in results if r["grade"] in ("FAIL", "GATHER")]
    if failed:
        print(f"\n--- Failed/Gather Only ({len(failed)}) ---")
        for r in failed:
            print(f"  {r['name']}: {r['error'][:80]}")

    # Write full report
    report_path = Path(__file__).parent.parent / "council_audit_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull report: {report_path}")


if __name__ == "__main__":
    asyncio.run(run_audit())
