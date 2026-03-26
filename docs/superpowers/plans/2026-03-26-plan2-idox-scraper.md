# Plan 2: Idox Platform Scraper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Idox platform scraper that handles ~250 UK councils (57% of all councils). This is the single highest-impact scraper — getting Idox working means majority coverage.

**Architecture:** One `IdoxScraper` class that takes a `CouncilConfig`, navigates the Idox search form, paginates results, and extracts application details from summary/dates/info tabs. Variant subclasses handle deviations (NI case prefixes, crumb layout, end-date exclusivity).

**Tech Stack:** httpx, beautifulsoup4, lxml (built on Plan 1 core infrastructure)

---

## File Structure

```
src/
├── platforms/
│   ├── __init__.py
│   └── idox.py              # IdoxScraper + variant classes
├── core/
│   └── (existing from Plan 1)
tests/
├── fixtures/
│   ├── idox_search_results.html
│   ├── idox_detail_summary.html
│   ├── idox_detail_dates.html
│   └── idox_detail_info.html
├── test_idox.py
└── test_idox_variants.py
```

---

### Task 1: Idox HTML Fixtures

**Files:**
- Create: `tests/fixtures/idox_search_results.html`
- Create: `tests/fixtures/idox_detail_summary.html`
- Create: `tests/fixtures/idox_detail_dates.html`
- Create: `tests/fixtures/idox_detail_info.html`

These are realistic HTML samples based on actual Idox portal structure, used by all subsequent tests.

- [ ] **Step 1: Create search results fixture**

```html
<!-- tests/fixtures/idox_search_results.html -->
<html><body>
<p class="pager top">
  <span class="showing">Showing 1-10 of 25</span>
  <a href="/online-applications/pagedSearchResults.do?action=page&amp;searchCriteria.page=2" class="next">Next</a>
</p>
<ul id="searchresults">
  <li class="searchresult">
    <a href="/online-applications/applicationDetails.do?activeTab=summary&amp;keyVal=ABC123">
      <span>View</span>
    </a>
    <p class="metainfo">
      No: <span>24/00001/FUL</span> |
      Received: <span>Mon 15 Jan 2024</span> |
      Validated: <span>Tue 16 Jan 2024</span>
    </p>
    <p class="address">123 High Street, Testtown, TT1 1AA</p>
    <p class="description">Erection of single storey rear extension</p>
  </li>
  <li class="searchresult">
    <a href="/online-applications/applicationDetails.do?activeTab=summary&amp;keyVal=DEF456">
      <span>View</span>
    </a>
    <p class="metainfo">
      No: <span>24/00002/HOU</span> |
      Received: <span>Wed 17 Jan 2024</span> |
      Validated: <span>Thu 18 Jan 2024</span>
    </p>
    <p class="address">456 Main Road, Testville, TV2 2BB</p>
    <p class="description">Construction of new detached dwelling with garage</p>
  </li>
</ul>
</body></html>
```

- [ ] **Step 2: Create detail summary fixture**

```html
<!-- tests/fixtures/idox_detail_summary.html -->
<html><body>
<div id="pa_tabs">
  <a id="subtab_summary" href="/online-applications/applicationDetails.do?activeTab=summary&amp;keyVal=ABC123" class="active">Summary</a>
  <a id="subtab_dates" href="/online-applications/applicationDetails.do?activeTab=dates&amp;keyVal=ABC123">Important Dates</a>
  <a id="subtab_details" href="/online-applications/applicationDetails.do?activeTab=details&amp;keyVal=ABC123">Further Information</a>
</div>
<table id="simpleDetailsTable">
  <tr><th>Reference</th><td>24/00001/FUL</td></tr>
  <tr><th>Alternative Reference</th><td>PP-12345678</td></tr>
  <tr><th>Application Received</th><td>Mon 15 Jan 2024</td></tr>
  <tr><th>Application Validated</th><td>Tue 16 Jan 2024</td></tr>
  <tr><th>Address</th><td>123 High Street, Testtown, TT1 1AA</td></tr>
  <tr><th>Proposal</th><td>Erection of single storey rear extension</td></tr>
  <tr><th>Status</th><td>Awaiting decision</td></tr>
  <tr><th>Appeal Status</th><td>Unknown</td></tr>
  <tr><th>Appeal Decision</th><td>Unknown</td></tr>
</table>
</body></html>
```

- [ ] **Step 3: Create detail dates fixture**

```html
<!-- tests/fixtures/idox_detail_dates.html -->
<html><body>
<table id="simpleDetailsTable">
  <tr><th>Application Received</th><td>Mon 15 Jan 2024</td></tr>
  <tr><th>Validated</th><td>Tue 16 Jan 2024</td></tr>
  <tr><th>Expiry Date</th><td>Mon 11 Mar 2024</td></tr>
  <tr><th>Target Date</th><td>Mon 11 Mar 2024</td></tr>
  <tr><th>Neighbour Consultation Expiry Date</th><td>Mon 05 Feb 2024</td></tr>
  <tr><th>Standard Consultation Expiry Date</th><td>Mon 05 Feb 2024</td></tr>
  <tr><th>Decision Made Date</th><td>Fri 08 Mar 2024</td></tr>
</table>
</body></html>
```

- [ ] **Step 4: Create detail info fixture**

```html
<!-- tests/fixtures/idox_detail_info.html -->
<html><body>
<table id="simpleDetailsTable">
  <tr><th>Application Type</th><td>Full Planning Permission</td></tr>
  <tr><th>Expected Decision Level</th><td>Delegated Decision</td></tr>
  <tr><th>Case Officer</th><td>John Smith</td></tr>
  <tr><th>Parish</th><td>Testtown Parish Council</td></tr>
  <tr><th>Ward</th><td>Testtown Ward</td></tr>
  <tr><th>District Reference</th><td>Hart</td></tr>
  <tr><th>Applicant Name</th><td>Mr J Doe</td></tr>
  <tr><th>Agent Name</th><td>ABC Architecture Ltd</td></tr>
  <tr><th>Agent Address</th><td>1 Design Street, London</td></tr>
</table>
</body></html>
```

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/
git commit -m "feat: add Idox HTML test fixtures"
```

---

### Task 2: Idox Selector Defaults & Config

**Files:**
- Create: `src/platforms/__init__.py`
- Create: `src/platforms/idox.py` (partial — selectors and config only, no scraping logic yet)
- Create: `tests/test_idox.py` (partial — selector tests only)

- [ ] **Step 1: Write failing tests for selector extraction**

```python
# tests/test_idox.py
import pytest
from pathlib import Path
from src.core.parser import PageParser
from src.platforms.idox import IDOX_SELECTORS, IDOX_DATES_SELECTORS, IDOX_INFO_SELECTORS, IDOX_SEARCH_SELECTORS


FIXTURES = Path(__file__).parent / "fixtures"


class TestIdoxSelectors:
    def setup_method(self):
        self.parser = PageParser()

    def test_search_results_extraction(self):
        html = (FIXTURES / "idox_search_results.html").read_text()
        results = self.parser.extract_list(html, IDOX_SEARCH_SELECTORS["result_links"], attr="href")
        assert len(results) == 2
        assert "ABC123" in results[0]
        assert "DEF456" in results[1]

    def test_search_results_uids(self):
        html = (FIXTURES / "idox_search_results.html").read_text()
        uids = self.parser.extract_list(html, IDOX_SEARCH_SELECTORS["result_uids"])
        assert len(uids) == 2
        assert uids[0] == "24/00001/FUL"
        assert uids[1] == "24/00002/HOU"

    def test_search_next_page(self):
        html = (FIXTURES / "idox_search_results.html").read_text()
        next_link = self.parser.select_one(html, IDOX_SEARCH_SELECTORS["next_page"])
        assert next_link is not None
        assert "page=2" in next_link["href"]

    def test_summary_page_extraction(self):
        html = (FIXTURES / "idox_detail_summary.html").read_text()
        data = self.parser.extract(html, IDOX_SELECTORS)
        assert data["reference"] == "24/00001/FUL"
        assert data["address"] == "123 High Street, Testtown, TT1 1AA"
        assert data["description"] == "Erection of single storey rear extension"
        assert data["status"] == "Awaiting decision"

    def test_dates_page_extraction(self):
        html = (FIXTURES / "idox_detail_dates.html").read_text()
        data = self.parser.extract(html, IDOX_DATES_SELECTORS)
        assert data["date_validated"] is not None
        assert "16 Jan 2024" in data["date_validated"]

    def test_info_page_extraction(self):
        html = (FIXTURES / "idox_detail_info.html").read_text()
        data = self.parser.extract(html, IDOX_INFO_SELECTORS)
        assert data["application_type"] == "Full Planning Permission"
        assert data["case_officer"] == "John Smith"
        assert data["parish"] == "Testtown Parish Council"
        assert data["ward"] == "Testtown Ward"
        assert data["applicant_name"] == "Mr J Doe"

    def test_tab_links_extraction(self):
        html = (FIXTURES / "idox_detail_summary.html").read_text()
        dates_link = self.parser.select_one(html, IDOX_SEARCH_SELECTORS["dates_tab"])
        info_link = self.parser.select_one(html, IDOX_SEARCH_SELECTORS["info_tab"])
        assert dates_link is not None
        assert "activeTab=dates" in dates_link["href"]
        assert info_link is not None
        assert "activeTab=details" in info_link["href"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_idox.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.platforms'`

- [ ] **Step 3: Implement selector constants**

```python
# src/platforms/__init__.py
# empty

# src/platforms/idox.py
"""Idox platform scraper for UK planning authorities.

Idox is the dominant planning portal platform, used by ~250 UK councils.
This module defines the default selectors and the scraper class.
"""

# Default CSS selectors for Idox search results pages
IDOX_SEARCH_SELECTORS = {
    "result_links": "ul#searchresults li.searchresult > a",
    "result_uids": "ul#searchresults li.searchresult p.metainfo > span:first-child",
    "next_page": "a.next",
    "dates_tab": "a#subtab_dates",
    "info_tab": "a#subtab_details",
}

# Default CSS selectors for Idox application summary page
IDOX_SELECTORS = {
    "reference": "th:-soup-contains('Reference') + td",
    "address": "th:-soup-contains('Address') + td",
    "description": "th:-soup-contains('Proposal') + td",
    "status": "th:-soup-contains('Status') + td",
    "alt_reference": "th:-soup-contains('Alternative Reference') + td",
}

# Default CSS selectors for Idox dates tab
IDOX_DATES_SELECTORS = {
    "date_received": "th:-soup-contains('Application Received') + td",
    "date_validated": "th:-soup-contains('Validated') + td",
    "expiry_date": "th:-soup-contains('Expiry Date') + td",
    "target_date": "th:-soup-contains('Target Date') + td",
    "decision_date": "th:-soup-contains('Decision Made Date') + td",
    "consultation_expiry": "th:-soup-contains('Standard Consultation Expiry') + td",
}

# Default CSS selectors for Idox further information tab
IDOX_INFO_SELECTORS = {
    "application_type": "th:-soup-contains('Application Type') + td",
    "case_officer": "th:-soup-contains('Case Officer') + td",
    "parish": "th:-soup-contains('Parish') + td",
    "ward": "th:-soup-contains('Ward') + td",
    "applicant_name": "th:-soup-contains('Applicant Name') + td",
    "agent_name": "th:-soup-contains('Agent Name') + td",
    "decision_level": "th:-soup-contains('Decision Level') + td",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_idox.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/platforms/__init__.py src/platforms/idox.py tests/test_idox.py
git commit -m "feat: add Idox default CSS selectors with fixture tests"
```

---

### Task 3: IdoxScraper — gather_ids

**Files:**
- Modify: `src/platforms/idox.py`
- Modify: `tests/test_idox.py`

- [ ] **Step 1: Write failing tests for gather_ids**

Add to `tests/test_idox.py`:

```python
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock
from src.platforms.idox import IdoxScraper, IDOX_SEARCH_SELECTORS
from src.core.config import CouncilConfig
from src.core.scraper import ApplicationSummary


FIXTURES = Path(__file__).parent / "fixtures"

SEARCH_RESULTS_HTML = (FIXTURES / "idox_search_results.html").read_text()

# Second page with no "next" link (last page)
SEARCH_RESULTS_LAST_PAGE = """
<html><body>
<p class="pager top">
  <span class="showing">Showing 11-12 of 12</span>
</p>
<ul id="searchresults">
  <li class="searchresult">
    <a href="/online-applications/applicationDetails.do?activeTab=summary&amp;keyVal=GHI789">
      <span>View</span>
    </a>
    <p class="metainfo">
      No: <span>24/00003/LBC</span> |
      Received: <span>Fri 19 Jan 2024</span>
    </p>
    <p class="address">789 Church Lane, Testbury</p>
    <p class="description">Listed building consent for window replacement</p>
  </li>
</ul>
</body></html>
"""

IDOX_CONFIG = CouncilConfig(
    name="Hart",
    authority_code="hart",
    platform="idox",
    base_url="https://publicaccess.hart.gov.uk/online-applications",
)


class TestIdoxGatherIds:
    async def test_gather_ids_single_page(self):
        scraper = IdoxScraper(config=IDOX_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(return_value=SEARCH_RESULTS_LAST_PAGE)
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            text=SEARCH_RESULTS_LAST_PAGE,
            headers={},
        ))
        scraper._client = mock_client

        results = await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))
        assert len(results) == 1
        assert results[0].uid == "24/00003/LBC"
        assert "GHI789" in results[0].url

    async def test_gather_ids_with_pagination(self):
        scraper = IdoxScraper(config=IDOX_CONFIG)
        mock_client = AsyncMock()

        # First call returns page with next link, second returns last page
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            text=SEARCH_RESULTS_HTML,
            headers={},
        ))
        mock_client.get_html = AsyncMock(side_effect=[
            SEARCH_RESULTS_HTML,      # search page load
            SEARCH_RESULTS_LAST_PAGE,  # page 2
        ])
        scraper._client = mock_client

        results = await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))
        assert len(results) == 3  # 2 from page 1 + 1 from page 2

    async def test_gather_ids_empty_results(self):
        scraper = IdoxScraper(config=IDOX_CONFIG)
        mock_client = AsyncMock()
        empty_html = '<html><body><ul id="searchresults"></ul></body></html>'
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            text=empty_html,
            headers={},
        ))
        mock_client.get_html = AsyncMock(return_value=empty_html)
        scraper._client = mock_client

        results = await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))
        assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_idox.py::TestIdoxGatherIds -v`
Expected: FAIL — `ImportError: cannot import name 'IdoxScraper'`

- [ ] **Step 3: Implement IdoxScraper.gather_ids**

Add to `src/platforms/idox.py`:

```python
from datetime import date, timedelta
from urllib.parse import urljoin

from src.core.browser import HttpClient
from src.core.config import CouncilConfig
from src.core.parser import PageParser
from src.core.scraper import ApplicationDetail, ApplicationSummary, BaseScraper, ScrapeResult


class IdoxScraper(BaseScraper):
    """Scraper for Idox-based planning portals (~250 UK councils)."""

    SEARCH_PATH = "/search.do?action=advanced"
    RESULTS_PATH = "/advancedSearchResults.do?action=firstPage"
    DATE_FORMAT = "%d/%m/%Y"

    # Form field names for date search
    DATE_FROM_FIELD = "date(applicationReceivedStart)"
    DATE_TO_FIELD = "date(applicationReceivedEnd)"
    SEARCH_TYPE_FIELD = "searchType"
    SEARCH_TYPE_VALUE = "Application"

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._parser = PageParser()
        self._client = HttpClient(
            timeout=30,
            rate_limit_delay=config.rate_limit_delay,
        )
        # Merge default selectors with council overrides
        self._search_selectors = {**IDOX_SEARCH_SELECTORS}
        self._summary_selectors = {**IDOX_SELECTORS}
        self._dates_selectors = {**IDOX_DATES_SELECTORS}
        self._info_selectors = {**IDOX_INFO_SELECTORS}
        if config.selectors:
            for key, val in config.selectors.items():
                for sel_dict in (self._search_selectors, self._summary_selectors,
                                 self._dates_selectors, self._info_selectors):
                    if key in sel_dict:
                        sel_dict[key] = val

    async def gather_ids(self, date_from: date, date_to: date) -> list[ApplicationSummary]:
        """Search Idox portal for applications in date range, handling pagination."""
        search_url = self.config.base_url + self.SEARCH_PATH

        # First load the search page (establishes session)
        await self._client.get_html(search_url)

        # Submit the search form
        results_url = self.config.base_url + self.RESULTS_PATH
        form_data = {
            self.DATE_FROM_FIELD: date_from.strftime(self.DATE_FORMAT),
            self.DATE_TO_FIELD: date_to.strftime(self.DATE_FORMAT),
            self.SEARCH_TYPE_FIELD: self.SEARCH_TYPE_VALUE,
        }
        response = await self._client.post(results_url, data=form_data)
        html = response.text

        applications = []
        while True:
            page_apps = self._parse_search_results(html)
            applications.extend(page_apps)

            next_el = self._parser.select_one(html, self._search_selectors["next_page"])
            if next_el is None:
                break
            next_url = urljoin(self.config.base_url, next_el["href"])
            html = await self._client.get_html(next_url)

        return applications

    def _parse_search_results(self, html: str) -> list[ApplicationSummary]:
        """Extract application summaries from a single results page."""
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
        """Fetch full details — implemented in Task 4."""
        raise NotImplementedError("fetch_detail not yet implemented")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_idox.py -v`
Expected: All 10 tests PASS (7 selector + 3 gather_ids)

- [ ] **Step 5: Commit**

```bash
git add src/platforms/idox.py tests/test_idox.py
git commit -m "feat: add IdoxScraper.gather_ids with pagination support"
```

---

### Task 4: IdoxScraper — fetch_detail

**Files:**
- Modify: `src/platforms/idox.py`
- Modify: `tests/test_idox.py`

- [ ] **Step 1: Write failing tests for fetch_detail**

Add to `tests/test_idox.py`:

```python
from src.core.scraper import ApplicationDetail

SUMMARY_HTML = (FIXTURES / "idox_detail_summary.html").read_text()
DATES_HTML = (FIXTURES / "idox_detail_dates.html").read_text()
INFO_HTML = (FIXTURES / "idox_detail_info.html").read_text()


class TestIdoxFetchDetail:
    async def test_fetch_detail_full(self):
        scraper = IdoxScraper(config=IDOX_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(side_effect=[SUMMARY_HTML, DATES_HTML, INFO_HTML])
        scraper._client = mock_client

        app = ApplicationSummary(
            uid="24/00001/FUL",
            url="https://publicaccess.hart.gov.uk/online-applications/applicationDetails.do?activeTab=summary&keyVal=ABC123",
        )
        detail = await scraper.fetch_detail(app)

        assert detail.reference == "24/00001/FUL"
        assert detail.address == "123 High Street, Testtown, TT1 1AA"
        assert detail.description == "Erection of single storey rear extension"
        assert detail.status == "Awaiting decision"
        assert detail.application_type == "Full Planning Permission"
        assert detail.case_officer == "John Smith"
        assert detail.parish == "Testtown Parish Council"
        assert detail.ward == "Testtown Ward"
        assert detail.applicant_name == "Mr J Doe"
        assert detail.raw_data is not None
        assert "date_validated" in detail.raw_data

    async def test_fetch_detail_missing_tabs(self):
        """If dates/info tabs are missing from summary page, still returns what it can."""
        no_tabs_html = """
        <html><body>
        <table id="simpleDetailsTable">
          <tr><th>Reference</th><td>24/00001/FUL</td></tr>
          <tr><th>Address</th><td>123 High Street</td></tr>
          <tr><th>Proposal</th><td>Test</td></tr>
        </table>
        </body></html>
        """
        scraper = IdoxScraper(config=IDOX_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(return_value=no_tabs_html)
        scraper._client = mock_client

        app = ApplicationSummary(uid="24/00001/FUL", url="https://example.com/app")
        detail = await scraper.fetch_detail(app)

        assert detail.reference == "24/00001/FUL"
        assert detail.address == "123 High Street"
        assert detail.application_type is None  # no info tab
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_idox.py::TestIdoxFetchDetail -v`
Expected: FAIL — `NotImplementedError`

- [ ] **Step 3: Implement fetch_detail**

Replace the `fetch_detail` stub in `src/platforms/idox.py`:

```python
    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        """Fetch full application details from summary, dates, and info tabs."""
        # Load summary page
        summary_html = await self._client.get_html(application.url)
        summary_data = self._parser.extract(summary_html, self._summary_selectors)

        # Attempt to load dates tab
        dates_data = {}
        dates_el = self._parser.select_one(summary_html, self._search_selectors["dates_tab"])
        if dates_el:
            dates_url = urljoin(self.config.base_url, dates_el["href"])
            dates_html = await self._client.get_html(dates_url)
            dates_data = self._parser.extract(dates_html, self._dates_selectors)

        # Attempt to load info tab
        info_data = {}
        info_el = self._parser.select_one(summary_html, self._search_selectors["info_tab"])
        if info_el:
            info_url = urljoin(self.config.base_url, info_el["href"])
            info_html = await self._client.get_html(info_url)
            info_data = self._parser.extract(info_html, self._info_selectors)

        # Merge all extracted data
        raw = {k: v for d in (summary_data, dates_data, info_data) for k, v in d.items() if v is not None}

        return ApplicationDetail(
            reference=summary_data.get("reference") or application.uid,
            address=summary_data.get("address") or "",
            description=summary_data.get("description") or "",
            url=application.url,
            application_type=info_data.get("application_type"),
            status=summary_data.get("status"),
            date_received=self._parse_date(dates_data.get("date_received")),
            date_validated=self._parse_date(dates_data.get("date_validated")),
            ward=info_data.get("ward"),
            parish=info_data.get("parish"),
            applicant_name=info_data.get("applicant_name"),
            case_officer=info_data.get("case_officer"),
            raw_data=raw,
        )

    @staticmethod
    def _parse_date(date_str: str | None) -> date | None:
        """Parse Idox date strings like 'Mon 15 Jan 2024' or '15/01/2024'."""
        if not date_str:
            return None
        from dateutil import parser as dateutil_parser
        try:
            return dateutil_parser.parse(date_str, dayfirst=True).date()
        except (ValueError, TypeError):
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_idox.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/platforms/idox.py tests/test_idox.py
git commit -m "feat: add IdoxScraper.fetch_detail with multi-tab extraction"
```

---

### Task 5: IdoxScraper — Full Pipeline (scrape method)

**Files:**
- Modify: `tests/test_idox.py`

- [ ] **Step 1: Write failing test for full pipeline**

Add to `tests/test_idox.py`:

```python
class TestIdoxFullPipeline:
    async def test_scrape_end_to_end(self):
        """Test the full scrape pipeline: gather_ids -> fetch_detail for each."""
        scraper = IdoxScraper(config=IDOX_CONFIG)
        mock_client = AsyncMock()

        # gather_ids will get search page then post form
        # fetch_detail will get summary, dates, info for each of 2 results
        mock_client.get_html = AsyncMock(side_effect=[
            SEARCH_RESULTS_LAST_PAGE,  # search page load (gather_ids)
            # fetch_detail for app 1
            SUMMARY_HTML,
            DATES_HTML,
            INFO_HTML,
        ])
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            text=SEARCH_RESULTS_LAST_PAGE,  # only 1 result to keep test simple
            headers={},
        ))
        scraper._client = mock_client

        result = await scraper.scrape(date(2024, 1, 1), date(2024, 1, 14))
        assert result.is_success
        assert len(result.applications) == 1
        assert result.applications[0].reference == "24/00001/FUL"
        assert result.applications[0].application_type == "Full Planning Permission"

    async def test_scrape_handles_error(self):
        """Test that scrape catches exceptions and returns error result."""
        scraper = IdoxScraper(config=IDOX_CONFIG)
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        scraper._client = mock_client

        result = await scraper.scrape(date(2024, 1, 1), date(2024, 1, 14))
        assert not result.is_success
        assert "Connection refused" in result.error
```

- [ ] **Step 2: Run tests to verify they pass**

The `scrape` method is already implemented in `BaseScraper` (Plan 1 Task 6). These tests verify the Idox implementation works with it.

Run: `pytest tests/test_idox.py -v`
Expected: All 14 tests PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_idox.py
git commit -m "feat: add Idox full pipeline tests"
```

---

### Task 6: Idox Variants

**Files:**
- Modify: `src/platforms/idox.py`
- Create: `tests/test_idox_variants.py`

- [ ] **Step 1: Write failing tests for variants**

```python
# tests/test_idox_variants.py
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock
from src.platforms.idox import (
    IdoxScraper,
    IdoxEndExcScraper,
    IdoxNIScraper,
    IdoxCrumbScraper,
)
from src.core.config import CouncilConfig
from src.core.scraper import ApplicationSummary


NI_CONFIG = CouncilConfig(
    name="Belfast",
    authority_code="belfast",
    platform="idox_ni",
    base_url="https://epicpublic.planningni.gov.uk/publicaccess",
)

ENDEXC_CONFIG = CouncilConfig(
    name="Blackpool",
    authority_code="blackpool",
    platform="idox_endexc",
    base_url="https://idoxpa.blackpool.gov.uk/online-applications",
)

CRUMB_CONFIG = CouncilConfig(
    name="Cheltenham",
    authority_code="cheltenham",
    platform="idox_crumb",
    base_url="https://publicaccess.cheltenham.gov.uk/online-applications",
)


class TestIdoxEndExcScraper:
    async def test_end_date_incremented(self):
        """IdoxEndExcScraper adds 1 day to end date for exclusive end-date servers."""
        scraper = IdoxEndExcScraper(config=ENDEXC_CONFIG)
        mock_client = AsyncMock()
        empty_html = '<html><body><ul id="searchresults"></ul></body></html>'
        mock_client.get_html = AsyncMock(return_value=empty_html)
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200, text=empty_html, headers={},
        ))
        scraper._client = mock_client

        await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))

        # Verify the posted date_to is 15th (14th + 1 day)
        call_args = mock_client.post.call_args
        form_data = call_args.kwargs.get("data") or call_args[1].get("data") or call_args[0][1]
        assert form_data[IdoxScraper.DATE_TO_FIELD] == "15/01/2024"


class TestIdoxNIScraper:
    async def test_ni_searches_by_case_prefix(self):
        """IdoxNIScraper iterates through case prefixes for NI councils."""
        config = CouncilConfig(
            name="Belfast",
            authority_code="belfast",
            platform="idox_ni",
            base_url="https://epicpublic.planningni.gov.uk/publicaccess",
        )
        scraper = IdoxNIScraper(config=config, case_prefixes=["LA04", "Z/20"])
        mock_client = AsyncMock()
        empty_html = '<html><body><ul id="searchresults"></ul></body></html>'
        mock_client.get_html = AsyncMock(return_value=empty_html)
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200, text=empty_html, headers={},
        ))
        scraper._client = mock_client

        await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))

        # Should have made one POST per case prefix (+ initial search page loads)
        assert mock_client.post.call_count == 2


class TestIdoxCrumbScraper:
    def test_crumb_selectors_differ(self):
        """IdoxCrumbScraper uses different selectors for breadcrumb layout."""
        crumb_scraper = IdoxCrumbScraper(config=CRUMB_CONFIG)
        standard_scraper = IdoxScraper(config=CouncilConfig(
            name="Standard", authority_code="std", platform="idox", base_url="https://example.com",
        ))
        # Crumb layout uses span.caseNumber instead of table-based reference selector
        assert crumb_scraper._summary_selectors["reference"] != standard_scraper._summary_selectors["reference"]
        assert "caseNumber" in crumb_scraper._summary_selectors["reference"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_idox_variants.py -v`
Expected: FAIL — `ImportError: cannot import name 'IdoxEndExcScraper'`

- [ ] **Step 3: Implement variant classes**

Add to `src/platforms/idox.py`:

```python
class IdoxEndExcScraper(IdoxScraper):
    """Variant for Idox servers with exclusive end dates.

    Some Idox installations treat the end date as exclusive (not included
    in results). This variant adds 1 day to compensate.
    """

    async def gather_ids(self, date_from: date, date_to: date) -> list[ApplicationSummary]:
        adjusted_to = date_to + timedelta(days=1)
        return await super().gather_ids(date_from, adjusted_to)


class IdoxNIScraper(IdoxScraper):
    """Variant for Northern Ireland Idox councils.

    NI councils require searching by case reference prefix in addition
    to date range. Each council has specific prefixes (e.g. Belfast: LA04, Z/20).
    """

    REF_FIELD = "searchCriteria.reference"

    def __init__(self, config: CouncilConfig, case_prefixes: list[str] | None = None):
        super().__init__(config)
        self._case_prefixes = case_prefixes or []

    async def gather_ids(self, date_from: date, date_to: date) -> list[ApplicationSummary]:
        if not self._case_prefixes:
            return await super().gather_ids(date_from, date_to)

        all_results = []
        seen_uids = set()
        for prefix in self._case_prefixes:
            results = await self._gather_ids_with_prefix(date_from, date_to, prefix)
            for app in results:
                if app.uid not in seen_uids:
                    seen_uids.add(app.uid)
                    all_results.append(app)
        return all_results

    async def _gather_ids_with_prefix(
        self, date_from: date, date_to: date, prefix: str
    ) -> list[ApplicationSummary]:
        """Search with a specific case prefix."""
        search_url = self.config.base_url + self.SEARCH_PATH
        await self._client.get_html(search_url)

        results_url = self.config.base_url + self.RESULTS_PATH
        form_data = {
            self.DATE_FROM_FIELD: date_from.strftime(self.DATE_FORMAT),
            self.DATE_TO_FIELD: date_to.strftime(self.DATE_FORMAT),
            self.SEARCH_TYPE_FIELD: self.SEARCH_TYPE_VALUE,
            self.REF_FIELD: prefix,
        }
        response = await self._client.post(results_url, data=form_data)
        html = response.text

        applications = []
        while True:
            page_apps = self._parse_search_results(html)
            applications.extend(page_apps)
            next_el = self._parser.select_one(html, self._search_selectors["next_page"])
            if next_el is None:
                break
            next_url = urljoin(self.config.base_url, next_el["href"])
            html = await self._client.get_html(next_url)

        return applications


# Crumb-style selectors for councils using breadcrumb layout
IDOX_CRUMB_SELECTORS = {
    "reference": "span.caseNumber",
    "address": "span.address",
    "description": "span.description",
    "status": "th:-soup-contains('Status') + td",
    "alt_reference": "th:-soup-contains('Alternative Reference') + td",
}


class IdoxCrumbScraper(IdoxScraper):
    """Variant for Idox portals using breadcrumb-style layout.

    Some Idox installations display application details in a different
    HTML structure using spans with specific classes instead of table rows.
    """

    def __init__(self, config: CouncilConfig):
        super().__init__(config)
        self._summary_selectors = {**IDOX_CRUMB_SELECTORS}
        if config.selectors:
            for key, val in config.selectors.items():
                if key in self._summary_selectors:
                    self._summary_selectors[key] = val
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_idox_variants.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/platforms/idox.py tests/test_idox_variants.py
git commit -m "feat: add Idox variant scrapers (EndExc, NI, Crumb)"
```

---

### Task 7: Sample Council YAML Configs

**Files:**
- Create: `src/config/councils/hart.yml`
- Create: `src/config/councils/belfast.yml`
- Create: `src/config/councils/blackpool.yml`
- Create: `src/config/councils/cheltenham.yml`

- [ ] **Step 1: Create sample configs**

```yaml
# src/config/councils/hart.yml
name: Hart
authority_code: hart
platform: idox
base_url: "https://publicaccess.hart.gov.uk/online-applications"
schedule: "0 3 * * *"
requires_js: false
```

```yaml
# src/config/councils/belfast.yml
name: Belfast
authority_code: belfast
platform: idox_ni
base_url: "https://epicpublic.planningni.gov.uk/publicaccess"
schedule: "0 4 * * *"
requires_js: false
variant: ni
fields:
  case_prefixes: "LA04,Z/20"
```

```yaml
# src/config/councils/blackpool.yml
name: Blackpool
authority_code: blackpool
platform: idox_endexc
base_url: "https://idoxpa.blackpool.gov.uk/online-applications"
schedule: "0 3 * * *"
requires_js: false
```

```yaml
# src/config/councils/cheltenham.yml
name: Cheltenham
authority_code: cheltenham
platform: idox_crumb
base_url: "https://publicaccess.cheltenham.gov.uk/online-applications"
schedule: "0 3 * * *"
requires_js: false
```

- [ ] **Step 2: Write test to verify configs load**

Add to `tests/test_idox.py`:

```python
class TestIdoxConfigs:
    def test_sample_configs_load(self):
        config_dir = Path(__file__).parent.parent / "src" / "config" / "councils"
        if not config_dir.exists():
            pytest.skip("No council configs directory")
        configs = load_all_councils(config_dir)
        assert len(configs) >= 4
        platforms = {c.platform for c in configs}
        assert "idox" in platforms
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_idox.py::TestIdoxConfigs -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/config/councils/ tests/test_idox.py
git commit -m "feat: add sample Idox council YAML configs"
```

---

## Summary

After completing this plan you will have:

- Realistic Idox HTML test fixtures
- Complete `IdoxScraper` with `gather_ids` (pagination) and `fetch_detail` (multi-tab extraction)
- Three variant scrapers: `IdoxEndExcScraper`, `IdoxNIScraper`, `IdoxCrumbScraper`
- CSS selector constants for all Idox page types
- Date parsing for Idox date formats
- Sample council YAML configs for each variant
- Config override merging (council YAML overrides platform defaults)
- Full test coverage with mocked HTTP responses

**Next plan:** Plan 3 — Scheduler & Orchestrator
