"""Boston Borough Council planning scraper.

Granicus/Firmstep platform behind Cloudflare at boston.gov.uk.
Requires Playwright for rendering. Search by reference prefix,
results rendered in DOM with B/YY/NNNN format references.
"""
import re
from datetime import date
from typing import List

from playwright.async_api import async_playwright

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper, ScrapeResult

BASE_URL = "https://www.boston.gov.uk/planningapplicationsearch"


class BostonScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        return []

    async def fetch_detail(self, app: ApplicationSummary) -> ApplicationDetail:
        return ApplicationDetail(reference=app.uid, address="", description="", url=app.url)

    async def scrape(self, date_from: date, date_to: date) -> ScrapeResult:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                ctx = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                page = await ctx.new_page()

                # Search by year prefix
                yr = str(date_to.year)[2:]
                await page.goto(BASE_URL, timeout=30000)
                await page.wait_for_timeout(3000)

                await page.fill(
                    '[name="PLANNINGAPPLICATIONSEARCHV3_SEARCH_REFERENCE"]',
                    f"B/{yr}/0",
                )
                await page.click('button:has-text("Search")')
                await page.wait_for_timeout(8000)

                # Extract results from DOM
                data = await page.evaluate("""() => {
                    const text = document.body.innerText;
                    const blocks = text.split(/(?=B\\/\\d{2}\\/\\d{4})/);
                    const results = [];
                    const seen = new Set();
                    for (const block of blocks) {
                        const refMatch = block.match(/^(B\\/\\d{2}\\/\\d{4})/);
                        if (!refMatch) continue;
                        const ref = refMatch[1];
                        if (seen.has(ref)) continue;
                        seen.add(ref);
                        const lines = block.split('\\n').filter(l => l.trim());
                        results.push({
                            ref,
                            address: lines[1] || '',
                            proposal: lines[2] || '',
                            status: lines[3] || '',
                        });
                    }
                    return results;
                }""")

                details = [
                    ApplicationDetail(
                        reference=d["ref"],
                        address=d.get("address", ""),
                        description=d.get("proposal", ""),
                        url=BASE_URL,
                        status=d.get("status"),
                    )
                    for d in data
                ]

                await browser.close()
            return ScrapeResult(date_from=date_from, date_to=date_to, applications=details)
        except Exception as e:
            return ScrapeResult(date_from=date_from, date_to=date_to, error=str(e))
