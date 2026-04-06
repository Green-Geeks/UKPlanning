"""Kensington and Chelsea (RBKC) planning scraper.

Tytl/SolidJS platform at atlas.rbkc.gov.uk/planningsearch.
Uses Playwright to render the SPA and extract data from the DOM.
Search results at /search/everywhere, detail at /cases/{ref}.
"""
import re
from datetime import date, datetime
from typing import List, Optional

from playwright.async_api import async_playwright

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper, ScrapeResult

BASE_URL = "https://atlas.rbkc.gov.uk/planningsearch"


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ["%d %b %Y", "%d %B %Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


class KensingtonScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        return []  # Use scrape() override

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        return ApplicationDetail(reference=application.uid, address="", description="", url=application.url)

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
                    viewport={"width": 1920, "height": 1080},
                )
                page = await ctx.new_page()
                await page.add_init_script(
                    'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
                )

                # Load search results
                await page.goto(f"{BASE_URL}/search/everywhere?sort=1", timeout=30000)
                await page.wait_for_timeout(8000)

                # Extract all application links and basic data
                apps_data = await page.evaluate("""() => {
                    const links = document.querySelectorAll('a[href*="/planningsearch/cases/"]');
                    return Array.from(links).map(a => {
                        const ref = a.innerText.replace('N°: ', '').trim();
                        return {ref, href: a.href};
                    });
                }""")

                details = []
                seen = set()

                # Visit each detail page (limit to reasonable number)
                for app in apps_data[:100]:
                    ref = app["ref"]
                    if ref in seen or not ref:
                        continue
                    seen.add(ref)

                    try:
                        await page.goto(app["href"], timeout=15000)
                        await page.wait_for_timeout(3000)

                        detail = await page.evaluate("""() => {
                            const text = document.querySelector('main')?.innerText || '';
                            const get = (label) => {
                                const match = text.match(new RegExp(label + '\\\\n([^\\\\n]+)'));
                                return match ? match[1].trim() : '';
                            };
                            return {
                                proposal: (() => {
                                    const m = text.match(/Proposed development:\\n\\n([\\s\\S]*?)\\n\\nLocation/);
                                    return m ? m[1].trim() : '';
                                })(),
                                location: get('Location'),
                                ward: get('Ward'),
                                applicant: get("Applicant's name"),
                                appType: get('Application type'),
                                received: get('Date received'),
                                registered: get('Registration date'),
                                status: get('Application status'),
                            };
                        }""")

                        received = _parse_date(detail.get("received", ""))
                        if received and (received < date_from or received > date_to):
                            continue

                        details.append(ApplicationDetail(
                            reference=ref,
                            address=detail.get("location", ""),
                            description=detail.get("proposal", ""),
                            url=app["href"],
                            application_type=detail.get("appType"),
                            status=detail.get("status"),
                            date_received=received,
                            date_validated=_parse_date(detail.get("registered", "")),
                            ward=detail.get("ward"),
                            applicant_name=detail.get("applicant"),
                        ))
                    except Exception:
                        continue

                await browser.close()

            return ScrapeResult(date_from=date_from, date_to=date_to, applications=details)
        except Exception as e:
            return ScrapeResult(date_from=date_from, date_to=date_to, error=str(e))
