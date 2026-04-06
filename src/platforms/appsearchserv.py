"""AppSearchServ platform scraper (Hartlepool, High Peak, Staffordshire Moorlands, Guernsey).

Legacy portal system using ApplicationSearchServlet. POST with date params,
results in HTML table with reference, dates, location, proposal, decision.
"""
import re
from datetime import date, datetime
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from src.core.config import CouncilConfig
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

COUNCIL_URLS = {
    "staffordshiremoorlands": "http://publicaccess.staffsmoorlands.gov.uk/portal/servlets/ApplicationSearchServlet",
    "hartlepool": "https://planning.hartlepool.gov.uk/portal/servlets/ApplicationSearchServlet",
    "highpeak": "http://planning.highpeak.gov.uk/portal/servlets/ApplicationSearchServlet",
    "guernsey": "http://planningexplorer.gov.gg/portal/servlets/ApplicationSearchServlet",
}


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ["%d/%m/%Y", "%d %b %Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


class AppSearchServScraper(BaseScraper):

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._search_url = COUNCIL_URLS.get(
            config.authority_code,
            config.base_url.rstrip("/")
        )
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=True,
            timeout=30,
            verify=False,
        )

    async def gather_ids(self, date_from: date, date_to: date) -> List[ApplicationSummary]:
        # Try multiple date field names — different councils use different names
        for from_field, to_field in [
            ("ReceivedDateFrom", "ReceivedDateTo"),
            ("ValidDateFrom", "ValidDateTo"),
        ]:
            resp = await self._client.post(self._search_url, data={
                from_field: date_from.strftime("%d/%m/%Y"),
                to_field: date_to.strftime("%d/%m/%Y"),
                "searchCriteria": "Search",
            })
            resp.raise_for_status()
            results = self._parse_results(resp.text)
            if results:
                return results
        return []

    def _parse_results(self, html: str) -> List[ApplicationSummary]:
        soup = BeautifulSoup(html, "html.parser")
        summaries = []

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            header_text = rows[0].get_text(strip=True).lower()
            if "application" not in header_text and "reference" not in header_text:
                continue

            for row in rows[1:]:
                cells = row.find_all("td")
                if not cells:
                    continue
                ref = cells[0].get_text(strip=True)
                link = row.find("a", href=True)
                url = link.get("href", "") if link else ""

                if ref:
                    summaries.append(ApplicationSummary(uid=ref, url=url))

        return summaries

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        # Re-scrape the search results to get row data (avoids detail page fetch)
        # For now, return minimal data — the gather step already has most fields
        return ApplicationDetail(
            reference=application.uid,
            address="",
            description="",
            url=application.url,
        )

    async def scrape(self, date_from: date, date_to: date):
        """Override to extract all data from the search results table."""
        from src.core.scraper import ScrapeResult
        try:
            resp = None
            for from_field, to_field in [
                ("ReceivedDateFrom", "ReceivedDateTo"),
                ("ValidDateFrom", "ValidDateTo"),
            ]:
                resp = await self._client.post(self._search_url, data={
                    from_field: date_from.strftime("%d/%m/%Y"),
                    to_field: date_to.strftime("%d/%m/%Y"),
                    "searchCriteria": "Search",
                })
                resp.raise_for_status()
                if re.search(r'\d{2,4}/\d{3,6}', resp.text):
                    break

            soup = BeautifulSoup(resp.text, "html.parser")
            details = []

            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                if len(rows) < 2:
                    continue
                header_text = rows[0].get_text(strip=True).lower()
                if "application" not in header_text and "reference" not in header_text:
                    continue

                # Parse headers to find column indices
                headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
                col = {}
                for j, h in enumerate(headers):
                    if "reference" in h or "application" in h:
                        col["ref"] = j
                    elif "location" in h or "address" in h or "site" in h:
                        col["addr"] = j
                    elif "proposal" in h or "development" in h or "description" in h:
                        col["desc"] = j
                    elif "received" in h:
                        col["received"] = j
                    elif "valid" in h:
                        col["valid"] = j
                    elif "decision" in h and "date" not in h:
                        col["decision"] = j

                for row in rows[1:]:
                    cells = row.find_all("td")
                    if len(cells) < 2:
                        continue
                    link = row.find("a", href=True)
                    url = link.get("href", "") if link else ""

                    def cell(key):
                        idx = col.get(key)
                        return cells[idx].get_text(strip=True).replace("\n", ", ").replace("\t", "") if idx is not None and idx < len(cells) else ""

                    details.append(ApplicationDetail(
                        reference=cell("ref"),
                        address=cell("addr"),
                        description=cell("desc"),
                        url=url,
                        date_received=_parse_date(cell("received")),
                        date_validated=_parse_date(cell("valid")),
                        decision=cell("decision") or None,
                    ))

            return ScrapeResult(date_from=date_from, date_to=date_to, applications=details)
        except Exception as e:
            return ScrapeResult(date_from=date_from, date_to=date_to, error=str(e))
