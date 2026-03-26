#!/usr/bin/env python3
"""Test a live scrape against a real council website.

Usage: python scripts/test_live_scrape.py [authority_code]
Default: hart (Idox council, confirmed responding)
"""
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from src.core.config import load_council_config
from src.scheduler.registry import ScraperRegistry

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"


async def test_scrape(authority_code: str):
    config_path = CONFIG_DIR / f"{authority_code}.yml"
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    config = load_council_config(config_path)
    print(f"Council: {config.name}")
    print(f"Platform: {config.platform}")
    print(f"Base URL: {config.base_url}")
    print()

    registry = ScraperRegistry()
    try:
        scraper = registry.create_scraper(config)
    except KeyError as e:
        print(f"Unsupported platform: {e}")
        sys.exit(1)

    date_to = date.today()
    date_from = date_to - timedelta(days=14)
    print(f"Searching {date_from} to {date_to}...")
    print()

    # Step 1: gather_ids
    try:
        ids = await scraper.gather_ids(date_from, date_to)
        print(f"Found {len(ids)} applications")
        if not ids:
            print("No applications found in date range. Try a wider range.")
            return
        for app in ids[:5]:
            print(f"  {app.uid} — {app.url}")
        if len(ids) > 5:
            print(f"  ... and {len(ids) - 5} more")
        print()
    except Exception as e:
        print(f"gather_ids FAILED: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 2: fetch_detail for first application
    first = ids[0]
    print(f"Fetching detail for {first.uid}...")
    try:
        detail = await scraper.fetch_detail(first)
        print(f"  Reference: {detail.reference}")
        print(f"  Address: {detail.address}")
        print(f"  Description: {detail.description}")
        print(f"  Type: {detail.application_type}")
        print(f"  Status: {detail.status}")
        print(f"  Received: {detail.date_received}")
        print(f"  Validated: {detail.date_validated}")
        print(f"  Ward: {detail.ward}")
        print(f"  Parish: {detail.parish}")
        print(f"  Case Officer: {detail.case_officer}")
        print(f"  URL: {detail.url}")
        if detail.raw_data:
            print(f"  Raw fields: {len(detail.raw_data)}")
        print()
        print("LIVE SCRAPE SUCCESSFUL")
    except Exception as e:
        print(f"fetch_detail FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "hart"
    asyncio.run(test_scrape(code))
