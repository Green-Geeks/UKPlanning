#!/usr/bin/env python3
"""Test scraping against all enabled councils.

Does a quick gather_ids for each enabled council and reports which work vs fail.
Outputs results to council_test_report.txt.
"""
import asyncio
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from src.core.config import load_all_councils
from src.scheduler.registry import ScraperRegistry

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"


async def test_council(config, registry, date_from, date_to):
    """Test gather_ids for one council. Returns (authority_code, status, count, error)."""
    try:
        scraper = registry.create_scraper(config)
    except KeyError as e:
        return (config.authority_code, "unsupported", 0, str(e))

    try:
        ids = await scraper.gather_ids(date_from, date_to)
        return (config.authority_code, "ok", len(ids), None)
    except Exception as e:
        return (config.authority_code, "error", 0, str(e)[:200])
    finally:
        if hasattr(scraper, "_client") and hasattr(scraper._client, "_client"):
            await scraper._client._client.aclose()


async def run_all():
    configs = load_all_councils(CONFIG_DIR)
    registry = ScraperRegistry()

    enabled = [c for c in configs if not hasattr(c, "enabled") or c.model_extra.get("enabled", True) is not False]
    # Filter by checking YAML content for enabled: false
    real_enabled = []
    for c in configs:
        yml_path = CONFIG_DIR / f"{c.authority_code}.yml"
        content = yml_path.read_text()
        if "enabled: false" not in content:
            real_enabled.append(c)

    supported = [c for c in real_enabled if c.platform in registry.list_platforms()]
    print(f"Total configs: {len(configs)}")
    print(f"Enabled: {len(real_enabled)}")
    print(f"Supported platform: {len(supported)}")
    print()

    date_to = date.today()
    date_from = date_to - timedelta(days=14)

    results = []
    for i, config in enumerate(supported):
        label = f"[{i+1}/{len(supported)}]"
        sys.stdout.write(f"\r{label} Testing {config.name}...                    ")
        sys.stdout.flush()
        result = await test_council(config, registry, date_from, date_to)
        results.append(result)
        code, status, count, error = result
        if status == "ok":
            sys.stdout.write(f"\r{label} {config.name}: OK ({count} apps)\n")
        else:
            sys.stdout.write(f"\r{label} {config.name}: FAIL - {error[:80]}\n")

    # Summary
    ok = [r for r in results if r[1] == "ok"]
    failed = [r for r in results if r[1] == "error"]
    unsupported = [r for r in results if r[1] == "unsupported"]

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(ok)} OK, {len(failed)} FAILED, {len(unsupported)} UNSUPPORTED")
    print(f"{'='*60}")

    if failed:
        print(f"\n--- Failed ({len(failed)}) ---")
        # Group by error type
        error_groups = {}
        for code, status, count, error in failed:
            key = error[:60] if error else "unknown"
            if key not in error_groups:
                error_groups[key] = []
            error_groups[key].append(code)

        for error, councils in sorted(error_groups.items(), key=lambda x: -len(x[1])):
            print(f"\n  {error}")
            for c in councils:
                print(f"    - {c}")

    # Write report
    report_path = Path(__file__).parent.parent / "council_test_report.txt"
    with open(report_path, "w") as f:
        f.write(f"status\tauthority_code\tapps_found\terror\n")
        for code, status, count, error in sorted(results, key=lambda r: (r[1], r[0])):
            f.write(f"{status}\t{code}\t{count}\t{error or ''}\n")
    print(f"\nFull report: {report_path}")


if __name__ == "__main__":
    asyncio.run(run_all())
