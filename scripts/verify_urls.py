#!/usr/bin/env python3
"""Check which council base URLs still respond.

Reads YAML configs and makes HEAD requests to each base_url.
Outputs a report of responsive, redirected, and dead URLs.
"""
import asyncio
from pathlib import Path

import httpx
import yaml


async def check_url(client: httpx.AsyncClient, config_path: Path) -> dict:
    """Check if a council's base URL responds."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    name = config.get("name", "")
    base_url = config.get("base_url", "")
    platform = config.get("platform", "")

    if not base_url:
        return {"name": name, "status": "no_url", "platform": platform}

    try:
        response = await client.head(base_url, follow_redirects=True, timeout=15)
        return {
            "name": name,
            "base_url": base_url,
            "status": "ok" if response.status_code < 400 else f"http_{response.status_code}",
            "status_code": response.status_code,
            "platform": platform,
            "final_url": str(response.url),
        }
    except httpx.TimeoutException:
        return {"name": name, "base_url": base_url, "status": "timeout", "platform": platform}
    except Exception as e:
        return {"name": name, "base_url": base_url, "status": "error", "error": str(e), "platform": platform}


async def verify_all(config_dir: Path, concurrency: int = 20):
    """Check all council URLs with limited concurrency."""
    configs = sorted(config_dir.glob("*.yml"))
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        headers={"User-Agent": "UKPlanningScraper/2.0 URL Check"},
    ) as client:
        async def limited_check(path):
            async with semaphore:
                return await check_url(client, path)

        results = await asyncio.gather(*[limited_check(p) for p in configs])

    ok = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] not in ("ok", "no_url")]
    no_url = [r for r in results if r["status"] == "no_url"]

    print(f"\n=== URL Verification Report ===")
    print(f"Total configs: {len(results)}")
    print(f"Responding: {len(ok)}")
    print(f"Failed: {len(failed)}")
    print(f"No URL: {len(no_url)}")

    if failed:
        print(f"\n--- Failed URLs ---")
        for r in sorted(failed, key=lambda x: x["name"]):
            print(f"  {r['name']}: {r['status']} — {r.get('base_url', '')}")

    report_path = config_dir.parent.parent.parent / "url_report.txt"
    with open(report_path, "w") as f:
        for r in sorted(results, key=lambda x: x["name"]):
            f.write(f"{r['name']}\t{r.get('platform', '')}\t{r['status']}\t{r.get('base_url', '')}\n")
    print(f"\nFull report: {report_path}")


if __name__ == "__main__":
    config_dir = Path(__file__).parent.parent / "src" / "config" / "councils"
    asyncio.run(verify_all(config_dir))
