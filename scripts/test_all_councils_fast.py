#!/usr/bin/env python3
"""Fast parallel test of all enabled councils.

Tests gather_ids concurrently (semaphore-limited) and reports results.
"""
import asyncio
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from src.core.config import load_all_councils
from src.scheduler.registry import ScraperRegistry

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"


async def test_council(config, registry, date_from, date_to, sem):
    async with sem:
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
                try:
                    await scraper._client._client.aclose()
                except Exception:
                    pass


async def run_all():
    import yaml
    configs = load_all_councils(CONFIG_DIR)
    registry = ScraperRegistry()

    real_enabled = []
    for c in configs:
        yml_path = CONFIG_DIR / f"{c.authority_code}.yml"
        data = yaml.safe_load(yml_path.read_text())
        if data.get("enabled") is not False:
            real_enabled.append(c)

    supported = [c for c in real_enabled if c.platform in registry.list_platforms()]
    print(f"Total: {len(configs)} | Enabled: {len(real_enabled)} | Supported: {len(supported)}")

    date_to = date.today()
    date_from = date_to - timedelta(days=14)

    sem = asyncio.Semaphore(15)
    start = time.time()

    tasks = [test_council(c, registry, date_from, date_to, sem) for c in supported]
    results = []
    done = 0
    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        done += 1
        code, status, count, error = result
        symbol = "OK" if status == "ok" else "FAIL"
        detail = f"({count} apps)" if status == "ok" else (error[:60] if error else "")
        sys.stdout.write(f"\r[{done}/{len(tasks)}] {code}: {symbol} {detail}                    \n")
        sys.stdout.flush()

    elapsed = time.time() - start

    ok = [r for r in results if r[1] == "ok"]
    failed = [r for r in results if r[1] == "error"]
    unsupported = [r for r in results if r[1] == "unsupported"]

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(ok)} OK, {len(failed)} FAILED, {len(unsupported)} UNSUPPORTED")
    print(f"Time: {elapsed:.0f}s")
    print(f"{'='*60}")

    if failed:
        print(f"\n--- Failed ({len(failed)}) ---")
        error_groups = {}
        for code, status, count, error in failed:
            # Categorize errors
            if "timeout" in (error or "").lower() or "timed out" in (error or "").lower():
                key = "TIMEOUT"
            elif "429" in (error or ""):
                key = "RATE_LIMITED"
            elif "ssl" in (error or "").lower():
                key = "SSL_ERROR"
            elif "connect" in (error or "").lower():
                key = "CONNECTION_ERROR"
            elif "404" in (error or "") or "not found" in (error or "").lower():
                key = "NOT_FOUND"
            else:
                key = (error or "unknown")[:80]
            error_groups.setdefault(key, []).append(code)

        for error, councils in sorted(error_groups.items(), key=lambda x: -len(x[1])):
            print(f"\n  {error} ({len(councils)}):")
            for c in sorted(councils):
                print(f"    - {c}")

    # Write report
    report_path = Path(__file__).parent.parent / "council_test_report.txt"
    with open(report_path, "w") as f:
        f.write(f"status\tauthority_code\tapps_found\terror\n")
        for code, status, count, error in sorted(results, key=lambda r: (r[1], r[0])):
            f.write(f"{status}\t{code}\t{count}\t{error or ''}\n")
    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    asyncio.run(run_all())
