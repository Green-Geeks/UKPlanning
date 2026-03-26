# Plan 5: PlanningExplorer & SwiftLG Scrapers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build PlanningExplorer (20 councils) and SwiftLG (21 councils) platform scrapers, adding ~40 more councils to coverage. Together with Idox (~250), this covers ~310 of 430 councils (72%).

**Architecture:** Same pattern as Idox — platform scraper class with CSS selectors, inheriting from BaseScraper. SwiftLG has multiple HTML layout variants handled via selector override dicts. Both platforms are server-rendered HTML using httpx.

**Tech Stack:** httpx, beautifulsoup4, lxml (from Plan 1)

---

## File Structure

```
src/
├── platforms/
│   ├── idox.py              # (existing)
│   ├── planning_explorer.py  # PlanningExplorer scraper
│   └── swiftlg.py           # SwiftLG scraper + variants
tests/
├── fixtures/
│   ├── pe_search_results.html
│   ├── pe_detail.html
│   ├── pe_dates.html
│   ├── swiftlg_search_results.html
│   └── swiftlg_detail.html
├── test_planning_explorer.py
└── test_swiftlg.py
```

---

### Task 1: PlanningExplorer Fixtures & Scraper

**Files:**
- Create: `tests/fixtures/pe_search_results.html`
- Create: `tests/fixtures/pe_detail.html`
- Create: `tests/fixtures/pe_dates.html`
- Create: `src/platforms/planning_explorer.py`
- Create: `tests/test_planning_explorer.py`

- [ ] **Step 1: Create HTML fixtures**

```html
<!-- tests/fixtures/pe_search_results.html -->
<html><body>
<div id="pageCenter">
<table class="display_table">
  <tr><th>Application Number</th><th>Address</th><th>Proposal</th></tr>
  <tr>
    <td><a href="/Northgate/PlanningExplorer/Generic/StdDetails.aspx?PT=Planning%20Applications%20On-Line&amp;TYPE=PL/PlanningPK.xml&amp;PARAM0=12345">24/00001/FUL</a></td>
    <td>123 High Street, Testtown</td>
    <td>Erection of rear extension</td>
  </tr>
  <tr>
    <td><a href="/Northgate/PlanningExplorer/Generic/StdDetails.aspx?PT=Planning%20Applications%20On-Line&amp;TYPE=PL/PlanningPK.xml&amp;PARAM0=12346">24/00002/HOU</a></td>
    <td>456 Main Road, Testville</td>
    <td>New detached garage</td>
  </tr>
</table>
<a href="/Northgate/PlanningExplorer/GeneralSearch.aspx?page=2"><img title="Go to next page" /></a>
</div>
</body></html>
```

```html
<!-- tests/fixtures/pe_detail.html -->
<html><body>
<h1>Details Page</h1>
<ul>
  <li><span>Application Number</span> 24/00001/FUL</li>
  <li><span>Application Registered</span> 15/01/2024</li>
  <li><span>Site Address</span> 123 High Street, Testtown, TT1 1AA</li>
  <li><span>Proposal</span> Erection of rear extension</li>
  <li><span>Application Type</span> Full Planning Permission</li>
  <li><span>Status</span> Awaiting decision</li>
  <li><span>Case Officer</span> Jane Smith</li>
  <li><span>Ward</span> Central Ward</li>
  <li><span>Parish</span> Testtown Parish</li>
</ul>
<a href="/Northgate/PlanningExplorer/Generic/StdDates.aspx?PT=Planning&amp;PARAM0=12345">Application Dates</a>
</body></html>
```

```html
<!-- tests/fixtures/pe_dates.html -->
<html><body>
<h1>Dates Page</h1>
<ul>
  <li><span>Received</span> 10/01/2024</li>
  <li><span>Validated</span> 15/01/2024</li>
  <li><span>Target Date</span> 11/03/2024</li>
  <li><span>Decision Date</span> 05/03/2024</li>
</ul>
</body></html>
```

- [ ] **Step 2: Write tests**

```python
# tests/test_planning_explorer.py
import pytest
from pathlib import Path
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from src.platforms.planning_explorer import (
    PlanningExplorerScraper,
    PE_SEARCH_SELECTORS,
    PE_DETAIL_SELECTORS,
    PE_DATES_SELECTORS,
)
from src.core.config import CouncilConfig
from src.core.parser import PageParser
from src.core.scraper import ApplicationSummary

FIXTURES = Path(__file__).parent / "fixtures"

PE_CONFIG = CouncilConfig(
    name="Birmingham",
    authority_code="birmingham",
    platform="planning_explorer",
    base_url="https://eplanning.birmingham.gov.uk/Northgate/PlanningExplorer",
)


class TestPESelectors:
    def setup_method(self):
        self.parser = PageParser()

    def test_search_results_links(self):
        html = (FIXTURES / "pe_search_results.html").read_text()
        links = self.parser.extract_list(html, PE_SEARCH_SELECTORS["result_links"], attr="href")
        assert len(links) == 2
        assert "12345" in links[0]

    def test_search_results_uids(self):
        html = (FIXTURES / "pe_search_results.html").read_text()
        uids = self.parser.extract_list(html, PE_SEARCH_SELECTORS["result_uids"])
        assert len(uids) == 2
        assert uids[0] == "24/00001/FUL"

    def test_next_page_link(self):
        html = (FIXTURES / "pe_search_results.html").read_text()
        next_el = self.parser.select_one(html, PE_SEARCH_SELECTORS["next_page"])
        assert next_el is not None

    def test_detail_extraction(self):
        html = (FIXTURES / "pe_detail.html").read_text()
        data = self.parser.extract(html, PE_DETAIL_SELECTORS)
        assert data["reference"] == "24/00001/FUL"
        assert "123 High Street" in data["address"]
        assert data["description"] == "Erection of rear extension"

    def test_dates_extraction(self):
        html = (FIXTURES / "pe_dates.html").read_text()
        data = self.parser.extract(html, PE_DATES_SELECTORS)
        assert data["date_received"] is not None
        assert "10/01/2024" in data["date_received"]


class TestPEGatherIds:
    async def test_gather_ids(self):
        html = (FIXTURES / "pe_search_results.html").read_text()
        last_page = html.replace(
            '<a href="/Northgate/PlanningExplorer/GeneralSearch.aspx?page=2"><img title="Go to next page" /></a>',
            ''
        )
        scraper = PlanningExplorerScraper(config=PE_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(return_value=last_page)
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200, text=last_page, headers={},
        ))
        scraper._client = mock_client

        results = await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))
        assert len(results) == 2
        assert results[0].uid == "24/00001/FUL"


class TestPEFetchDetail:
    async def test_fetch_detail(self):
        detail_html = (FIXTURES / "pe_detail.html").read_text()
        dates_html = (FIXTURES / "pe_dates.html").read_text()

        scraper = PlanningExplorerScraper(config=PE_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(side_effect=[detail_html, dates_html])
        scraper._client = mock_client

        app = ApplicationSummary(uid="24/00001/FUL", url="https://example.com/detail")
        detail = await scraper.fetch_detail(app)

        assert detail.reference == "24/00001/FUL"
        assert detail.application_type == "Full Planning Permission"
        assert detail.case_officer == "Jane Smith"
        assert detail.parish == "Testtown Parish"
```

- [ ] **Step 3: Implement PlanningExplorer scraper**

```python
# src/platforms/planning_explorer.py
"""PlanningExplorer platform scraper for UK planning authorities.

Used by ~20 councils including Birmingham, Liverpool, Camden.
Two-page detail retrieval: details page + separate dates page.
"""
from datetime import date, timedelta
from urllib.parse import urljoin

from src.core.browser import HttpClient
from src.core.config import CouncilConfig
from src.core.parser import PageParser
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

PE_SEARCH_SELECTORS = {
    "result_links": "table.display_table td a",
    "result_uids": "table.display_table td a",
    "next_page": "a:has(img[title='Go to next page'])",
    "dates_link": "a:-soup-contains('Application Dates')",
}

PE_DETAIL_SELECTORS = {
    "reference": "li:has(span:-soup-contains('Application Number'))",
    "address": "li:has(span:-soup-contains('Site Address'))",
    "description": "li:has(span:-soup-contains('Proposal'))",
    "date_validated": "li:has(span:-soup-contains('Application Registered'))",
    "application_type": "li:has(span:-soup-contains('Application Type'))",
    "status": "li:has(span:-soup-contains('Status'))",
    "case_officer": "li:has(span:-soup-contains('Case Officer'))",
    "ward": "li:has(span:-soup-contains('Ward'))",
    "parish": "li:has(span:-soup-contains('Parish'))",
}

PE_DATES_SELECTORS = {
    "date_received": "li:has(span:-soup-contains('Received'))",
    "date_validated": "li:has(span:-soup-contains('Validated'))",
    "target_date": "li:has(span:-soup-contains('Target Date'))",
    "decision_date": "li:has(span:-soup-contains('Decision Date'))",
}


class PlanningExplorerScraper(BaseScraper):
    """Scraper for PlanningExplorer-based portals (~20 UK councils)."""

    SEARCH_PATH = "/GeneralSearch.aspx"
    DATE_FORMAT = "%d/%m/%Y"
    DATE_FROM_FIELD = "dateStart"
    DATE_TO_FIELD = "dateEnd"

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._parser = PageParser()
        self._client = HttpClient(timeout=30, rate_limit_delay=config.rate_limit_delay)
        self._search_selectors = {**PE_SEARCH_SELECTORS}
        self._detail_selectors = {**PE_DETAIL_SELECTORS}
        self._dates_selectors = {**PE_DATES_SELECTORS}
        if config.selectors:
            for key, val in config.selectors.items():
                for sel_dict in (self._search_selectors, self._detail_selectors, self._dates_selectors):
                    if key in sel_dict:
                        sel_dict[key] = val

    async def gather_ids(self, date_from: date, date_to: date) -> list:
        search_url = self.config.base_url + self.SEARCH_PATH
        await self._client.get_html(search_url)

        form_data = {
            self.DATE_FROM_FIELD: date_from.strftime(self.DATE_FORMAT),
            self.DATE_TO_FIELD: date_to.strftime(self.DATE_FORMAT),
        }
        response = await self._client.post(search_url, data=form_data)
        html = response.text

        applications = []
        while True:
            page_apps = self._parse_results(html)
            applications.extend(page_apps)
            next_el = self._parser.select_one(html, self._search_selectors["next_page"])
            if next_el is None:
                break
            next_url = urljoin(self.config.base_url, next_el.get("href", ""))
            html = await self._client.get_html(next_url)

        return applications

    def _parse_results(self, html: str) -> list:
        links = self._parser.extract_list(html, self._search_selectors["result_links"], attr="href")
        uids = self._parser.extract_list(html, self._search_selectors["result_uids"])
        results = []
        for i, link in enumerate(links):
            uid = uids[i] if i < len(uids) else None
            if uid:
                abs_url = urljoin(self.config.base_url, link)
                results.append(ApplicationSummary(uid=uid, url=abs_url))
        return results

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        detail_html = await self._client.get_html(application.url)
        detail_data = self._extract_li_fields(detail_html, self._detail_selectors)

        dates_data = {}
        dates_el = self._parser.select_one(detail_html, self._search_selectors["dates_link"])
        if dates_el:
            dates_url = urljoin(self.config.base_url, dates_el.get("href", ""))
            dates_html = await self._client.get_html(dates_url)
            dates_data = self._extract_li_fields(dates_html, self._dates_selectors)

        raw = {k: v for d in (detail_data, dates_data) for k, v in d.items() if v is not None}

        return ApplicationDetail(
            reference=detail_data.get("reference") or application.uid,
            address=detail_data.get("address") or "",
            description=detail_data.get("description") or "",
            url=application.url,
            application_type=detail_data.get("application_type"),
            status=detail_data.get("status"),
            date_received=self._parse_date(dates_data.get("date_received")),
            date_validated=self._parse_date(detail_data.get("date_validated")),
            ward=detail_data.get("ward"),
            parish=detail_data.get("parish"),
            case_officer=detail_data.get("case_officer"),
            raw_data=raw,
        )

    def _extract_li_fields(self, html: str, selectors: dict) -> dict:
        """Extract fields from <li><span>Label</span> Value</li> structure."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        result = {}
        for field_name, selector in selectors.items():
            el = soup.select_one(selector)
            if el:
                span = el.find("span")
                if span:
                    span.decompose()
                result[field_name] = el.get_text(strip=True)
            else:
                result[field_name] = None
        return result

    @staticmethod
    def _parse_date(date_str):
        if not date_str:
            return None
        from dateutil import parser as dateutil_parser
        try:
            return dateutil_parser.parse(date_str, dayfirst=True).date()
        except (ValueError, TypeError):
            return None
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_planning_explorer.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Register in scraper registry**

Edit `src/scheduler/registry.py` to add:
```python
from src.platforms.planning_explorer import PlanningExplorerScraper
```
And in `__init__`:
```python
"planning_explorer": PlanningExplorerScraper,
```

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/pe_*.html src/platforms/planning_explorer.py tests/test_planning_explorer.py src/scheduler/registry.py
git commit -m "feat: add PlanningExplorer platform scraper (20 councils)"
```

---

### Task 2: SwiftLG Fixtures & Scraper

**Files:**
- Create: `tests/fixtures/swiftlg_search_results.html`
- Create: `tests/fixtures/swiftlg_detail.html`
- Create: `src/platforms/swiftlg.py`
- Create: `tests/test_swiftlg.py`

- [ ] **Step 1: Create HTML fixtures**

```html
<!-- tests/fixtures/swiftlg_search_results.html -->
<html><body>
<p>Search results: 25</p>
<form>
<table>
  <tr><th>Reference</th><th>Address</th><th>Description</th></tr>
  <tr>
    <td><a href="WPHAPPDETAIL.DisplayUrl?theApnID=24%2F00001%2FFUL">24/00001/FUL</a></td>
    <td>123 High Street, Testtown</td>
    <td>Rear extension</td>
  </tr>
  <tr>
    <td><a href="WPHAPPDETAIL.DisplayUrl?theApnID=24%2F00002%2FHOU">24/00002/HOU</a></td>
    <td>456 Main Road, Testville</td>
    <td>New garage</td>
  </tr>
</table>
Pages <a href="?StartIndex=11">2</a>
</form>
</body></html>
```

```html
<!-- tests/fixtures/swiftlg_detail.html -->
<html><body>
<form action="WPHAPPDETAIL">
  <span>Application Ref:</span> <p>24/00001/FUL</p>
  <span>Registration Date:</span> <p>15/01/2024</p>
  <span>Main Location:</span> <p>123 High Street, Testtown, TT1 1AA</p>
  <span>Full Description:</span> <p>Erection of single storey rear extension</p>
  <span>Application Type:</span> <p>Full Planning Permission</p>
  <span>Application Date:</span> <p>10/01/2024</p>
  <span>Decision:</span> <p>Granted</p>
  <span>Case Officer:</span> <p>John Smith</p>
</form>
</body></html>
```

- [ ] **Step 2: Write tests**

```python
# tests/test_swiftlg.py
import pytest
from pathlib import Path
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from src.platforms.swiftlg import (
    SwiftLGScraper,
    SWIFTLG_SEARCH_SELECTORS,
    SWIFTLG_SPAN_SELECTORS,
)
from src.core.config import CouncilConfig
from src.core.parser import PageParser
from src.core.scraper import ApplicationSummary

FIXTURES = Path(__file__).parent / "fixtures"

SWIFTLG_CONFIG = CouncilConfig(
    name="Dudley",
    authority_code="dudley",
    platform="swiftlg",
    base_url="https://www5.dudley.gov.uk/swiftlg/apas/run",
)


class TestSwiftLGSelectors:
    def setup_method(self):
        self.parser = PageParser()

    def test_search_results_links(self):
        html = (FIXTURES / "swiftlg_search_results.html").read_text()
        links = self.parser.extract_list(html, SWIFTLG_SEARCH_SELECTORS["result_links"], attr="href")
        assert len(links) == 2

    def test_search_results_uids(self):
        html = (FIXTURES / "swiftlg_search_results.html").read_text()
        uids = self.parser.extract_list(html, SWIFTLG_SEARCH_SELECTORS["result_uids"])
        assert len(uids) == 2
        assert uids[0] == "24/00001/FUL"

    def test_detail_extraction(self):
        html = (FIXTURES / "swiftlg_detail.html").read_text()
        data = self.parser.extract(html, SWIFTLG_SPAN_SELECTORS)
        assert data["reference"] is not None
        assert data["description"] is not None


class TestSwiftLGGatherIds:
    async def test_gather_ids(self):
        last_page = (FIXTURES / "swiftlg_search_results.html").read_text()
        last_page = last_page.replace('Pages <a href="?StartIndex=11">2</a>', 'Pages')

        scraper = SwiftLGScraper(config=SWIFTLG_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(return_value=last_page)
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200, text=last_page, headers={},
        ))
        scraper._client = mock_client

        results = await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))
        assert len(results) == 2
        assert results[0].uid == "24/00001/FUL"


class TestSwiftLGFetchDetail:
    async def test_fetch_detail(self):
        detail_html = (FIXTURES / "swiftlg_detail.html").read_text()

        scraper = SwiftLGScraper(config=SWIFTLG_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(return_value=detail_html)
        scraper._client = mock_client

        app = ApplicationSummary(uid="24/00001/FUL", url="https://example.com/detail")
        detail = await scraper.fetch_detail(app)

        assert detail.reference == "24/00001/FUL"
        assert "123 High Street" in detail.address
        assert detail.description == "Erection of single storey rear extension"
```

- [ ] **Step 3: Implement SwiftLG scraper**

```python
# src/platforms/swiftlg.py
"""SwiftLG platform scraper for UK planning authorities.

Used by ~21 councils. Has multiple HTML layout variants (span, label, bold, strong)
handled via different selector dicts.
"""
from datetime import date
from urllib.parse import urljoin

from src.core.browser import HttpClient
from src.core.config import CouncilConfig
from src.core.parser import PageParser
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper

SWIFTLG_SEARCH_SELECTORS = {
    "result_links": "form table td a",
    "result_uids": "form table td a",
    "next_page": "form a[href*='StartIndex']",
}

SWIFTLG_SPAN_SELECTORS = {
    "reference": "span:-soup-contains('Application Ref') + p",
    "date_validated": "span:-soup-contains('Registration Date') + p",
    "address": "span:-soup-contains('Main Location') + p",
    "description": "span:-soup-contains('Full Description') + p",
    "application_type": "span:-soup-contains('Application Type') + p",
    "date_received": "span:-soup-contains('Application Date') + p",
    "decision": "span:-soup-contains('Decision') + p",
    "case_officer": "span:-soup-contains('Case Officer') + p",
}

SWIFTLG_LABEL_SELECTORS = {
    "reference": "label:-soup-contains('Reference') + p",
    "date_validated": "label:-soup-contains('Registration Date') + p",
    "address": "label:-soup-contains('Main Location') + p",
    "description": "label:-soup-contains('Full Description') + p",
    "application_type": "label:-soup-contains('Application Type') + p",
    "date_received": "label:-soup-contains('Application Date') + p",
    "decision": "label:-soup-contains('Decision') + p",
    "case_officer": "label:-soup-contains('Case Officer') + p",
}


class SwiftLGScraper(BaseScraper):
    """Scraper for SwiftLG-based portals (~21 UK councils)."""

    SEARCH_PATH = "/wphappcriteria.display"
    DATE_FORMAT = "%d/%m/%Y"
    DATE_FROM_FIELD = "REGFROMDATE.MAINBODY.WPACIS.1"
    DATE_TO_FIELD = "REGTODATE.MAINBODY.WPACIS.1"

    def __init__(self, config: CouncilConfig, detail_selectors: dict = None):
        super().__init__(config)
        self._parser = PageParser()
        self._client = HttpClient(timeout=30, rate_limit_delay=config.rate_limit_delay)
        self._search_selectors = {**SWIFTLG_SEARCH_SELECTORS}
        self._detail_selectors = detail_selectors or {**SWIFTLG_SPAN_SELECTORS}
        if config.selectors:
            for key, val in config.selectors.items():
                for sel_dict in (self._search_selectors, self._detail_selectors):
                    if key in sel_dict:
                        sel_dict[key] = val

    async def gather_ids(self, date_from: date, date_to: date) -> list:
        search_url = self.config.base_url + self.SEARCH_PATH
        await self._client.get_html(search_url)

        form_data = {
            self.DATE_FROM_FIELD: date_from.strftime(self.DATE_FORMAT),
            self.DATE_TO_FIELD: date_to.strftime(self.DATE_FORMAT),
        }
        response = await self._client.post(search_url, data=form_data)
        html = response.text

        applications = []
        while True:
            page_apps = self._parse_results(html)
            applications.extend(page_apps)
            next_el = self._parser.select_one(html, self._search_selectors["next_page"])
            if next_el is None:
                break
            next_url = urljoin(self.config.base_url, next_el.get("href", ""))
            html = await self._client.get_html(next_url)

        return applications

    def _parse_results(self, html: str) -> list:
        links = self._parser.extract_list(html, self._search_selectors["result_links"], attr="href")
        uids = self._parser.extract_list(html, self._search_selectors["result_uids"])
        results = []
        for i, link in enumerate(links):
            uid = uids[i] if i < len(uids) else None
            if uid:
                abs_url = urljoin(self.config.base_url, link)
                results.append(ApplicationSummary(uid=uid, url=abs_url))
        return results

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        html = await self._client.get_html(application.url)
        data = self._parser.extract(html, self._detail_selectors)

        raw = {k: v for k, v in data.items() if v is not None}

        return ApplicationDetail(
            reference=data.get("reference") or application.uid,
            address=data.get("address") or "",
            description=data.get("description") or "",
            url=application.url,
            application_type=data.get("application_type"),
            status=data.get("decision"),
            date_received=self._parse_date(data.get("date_received")),
            date_validated=self._parse_date(data.get("date_validated")),
            case_officer=data.get("case_officer"),
            raw_data=raw,
        )

    @staticmethod
    def _parse_date(date_str):
        if not date_str:
            return None
        from dateutil import parser as dateutil_parser
        try:
            return dateutil_parser.parse(date_str, dayfirst=True).date()
        except (ValueError, TypeError):
            return None


class SwiftLGLabelScraper(SwiftLGScraper):
    """Variant using <label> tags instead of <span> tags."""

    def __init__(self, config: CouncilConfig):
        super().__init__(config, detail_selectors={**SWIFTLG_LABEL_SELECTORS})
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_swiftlg.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Register in scraper registry**

Edit `src/scheduler/registry.py` to add:
```python
from src.platforms.swiftlg import SwiftLGScraper, SwiftLGLabelScraper
```
And in `__init__`:
```python
"swiftlg": SwiftLGScraper,
"swiftlg_label": SwiftLGLabelScraper,
```

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/swiftlg_*.html src/platforms/swiftlg.py tests/test_swiftlg.py src/scheduler/registry.py
git commit -m "feat: add SwiftLG platform scraper with label variant (21 councils)"
```

---

## Summary

After completing this plan you will have:

- PlanningExplorer scraper with two-page detail extraction (20 councils)
- SwiftLG scraper with span/label variants (21 councils)
- Both registered in the scraper registry
- ~12 new tests

**Platform coverage after this plan:**
- Idox: ~250 councils
- PlanningExplorer: ~20 councils
- SwiftLG: ~21 councils
- **Total: ~291 of 430 (68%)**

**Next plan:** Plan 6 — Migration (extract all council configs from old codebase)
