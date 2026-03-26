# Plan 1: Core Infrastructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up the modern Python project skeleton, base scraper classes, config system, browser abstraction, HTML parser, database models, and Docker Compose — everything platform scrapers need to build on.

**Architecture:** Fresh Python 3.12+ project using httpx/Playwright for HTTP, BS4+lxml for parsing, SQLAlchemy+Alembic for Postgres, and Pydantic for config validation. Council configs are YAML files that merge with platform defaults.

**Tech Stack:** Python 3.12+, httpx, playwright, beautifulsoup4, lxml, sqlalchemy, alembic, pydantic, pyyaml, pytest, Docker Compose, PostgreSQL

---

## File Structure

```
ukplanning/
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── scraper.py       # Abstract base scraper + data models (ApplicationSummary, ApplicationDetail, ScrapeResult)
│   │   ├── browser.py        # HttpClient and PlaywrightClient behind common interface
│   │   ├── parser.py         # CSS-selector-driven HTML field extraction
│   │   ├── config.py         # Pydantic models for council YAML configs + loader
│   │   ├── models.py         # SQLAlchemy ORM models (Council, Application, ScrapeRun)
│   │   └── database.py       # Engine/session factory, connection helpers
│   └── config/
│       └── councils/         # YAML files per council (populated later by migration plan)
├── migrations/
│   └── env.py                # Alembic environment
├── alembic.ini
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Shared fixtures (test DB, sample HTML)
│   ├── test_parser.py
│   ├── test_browser.py
│   ├── test_config.py
│   ├── test_scraper.py
│   └── test_models.py
├── pyproject.toml
├── docker-compose.yml
└── .env.example
```

---

### Task 1: Project Skeleton & Dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `src/__init__.py`
- Create: `src/core/__init__.py`
- Create: `src/config/councils/.gitkeep`
- Create: `tests/__init__.py`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `.gitignore` (replace existing)

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "ukplanning"
version = "2.0.0"
description = "Scrapers for UK planning authority websites"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "playwright>=1.40",
    "sqlalchemy[asyncio]>=2.0",
    "alembic>=1.13",
    "psycopg2-binary>=2.9",
    "pydantic>=2.5",
    "pydantic-settings>=2.1",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-httpx>=0.30",
    "aiosqlite>=0.20",
]

[build-system]
requires = ["setuptools>=69.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[tool.setuptools.packages.find]
where = ["."]
include = ["src*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: ukplanning
      POSTGRES_USER: ukplanning
      POSTGRES_PASSWORD: ${DB_PASSWORD:-devpassword}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

- [ ] **Step 3: Create .env.example**

```
DATABASE_URL=postgresql://ukplanning:devpassword@localhost:5432/ukplanning
DB_PASSWORD=devpassword
```

- [ ] **Step 4: Create .gitignore (replace existing)**

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.eggs/
*.egg
.env
.venv/
venv/
logs/
*.log
.pytest_cache/
.coverage
htmlcov/
```

- [ ] **Step 5: Create package init files and councils directory**

Create `src/__init__.py` — empty file.

Create `src/core/__init__.py` — empty file.

Create `tests/__init__.py` — empty file.

Create `src/config/councils/.gitkeep` — empty file.

- [ ] **Step 6: Install dependencies and verify**

Run: `pip install -e ".[dev]"`
Expected: All dependencies install without errors.

Run: `python -c "import httpx, bs4, lxml, sqlalchemy, pydantic, yaml; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml docker-compose.yml .env.example .gitignore src/__init__.py src/core/__init__.py tests/__init__.py src/config/councils/.gitkeep
git commit -m "feat: project skeleton with dependencies and docker-compose"
```

---

### Task 2: HTML Parser

**Files:**
- Create: `src/core/parser.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_parser.py
from src.core.parser import PageParser


SAMPLE_IDOX_DETAIL = """
<html><body>
<table>
  <tr><th>Reference</th><td>24/01234/FUL</td></tr>
  <tr><th>Address</th><td>123 High Street, London</td></tr>
  <tr><th>Proposal</th><td>Erection of new dwelling</td></tr>
  <tr><th>Status</th><td>Pending Consideration</td></tr>
</table>
</body></html>
"""

SAMPLE_IDOX_RESULTS = """
<html><body>
<ul id="searchresults">
  <li>
    <a href="/application/123">View</a>
    <p class="metainfo">No: APP/001 <span>received</span></p>
  </li>
  <li>
    <a href="/application/456">View</a>
    <p class="metainfo">No: APP/002 <span>received</span></p>
  </li>
</ul>
</body></html>
"""

SAMPLE_EMPTY = "<html><body><p>No results found</p></body></html>"


class TestPageParser:
    def test_extract_single_fields(self):
        parser = PageParser()
        selectors = {
            "reference": "th:-soup-contains('Reference') + td",
            "address": "th:-soup-contains('Address') + td",
            "description": "th:-soup-contains('Proposal') + td",
        }
        result = parser.extract(SAMPLE_IDOX_DETAIL, selectors)
        assert result["reference"] == "24/01234/FUL"
        assert result["address"] == "123 High Street, London"
        assert result["description"] == "Erection of new dwelling"

    def test_extract_missing_field_returns_none(self):
        parser = PageParser()
        selectors = {
            "reference": "th:-soup-contains('Reference') + td",
            "parish": "th:-soup-contains('Parish') + td",
        }
        result = parser.extract(SAMPLE_IDOX_DETAIL, selectors)
        assert result["reference"] == "24/01234/FUL"
        assert result["parish"] is None

    def test_extract_list(self):
        parser = PageParser()
        selector = "ul#searchresults li a"
        result = parser.extract_list(SAMPLE_IDOX_RESULTS, selector, attr="href")
        assert result == ["/application/123", "/application/456"]

    def test_extract_list_text(self):
        parser = PageParser()
        selector = "ul#searchresults li p.metainfo"
        result = parser.extract_list(SAMPLE_IDOX_RESULTS, selector)
        assert len(result) == 2
        assert "APP/001" in result[0]

    def test_extract_list_empty(self):
        parser = PageParser()
        selector = "ul#searchresults li a"
        result = parser.extract_list(SAMPLE_EMPTY, selector)
        assert result == []

    def test_extract_with_custom_transform(self):
        parser = PageParser()
        selectors = {
            "status": "th:-soup-contains('Status') + td",
        }
        transforms = {
            "status": lambda v: v.lower().replace(" ", "_"),
        }
        result = parser.extract(SAMPLE_IDOX_DETAIL, selectors, transforms=transforms)
        assert result["status"] == "pending_consideration"

    def test_select_one_element(self):
        parser = PageParser()
        element = parser.select_one(SAMPLE_IDOX_DETAIL, "th:-soup-contains('Reference') + td")
        assert element is not None
        assert element.get_text(strip=True) == "24/01234/FUL"

    def test_select_one_missing_returns_none(self):
        parser = PageParser()
        element = parser.select_one(SAMPLE_IDOX_DETAIL, "th:-soup-contains('Parish') + td")
        assert element is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.core.parser'`

- [ ] **Step 3: Write the parser implementation**

```python
# src/core/parser.py
from bs4 import BeautifulSoup, Tag
from typing import Callable


class PageParser:
    """CSS-selector-driven HTML field extraction."""

    def __init__(self, parser: str = "lxml"):
        self._parser = parser

    def _soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, self._parser)

    def select_one(self, html: str, selector: str) -> Tag | None:
        """Select a single element from HTML."""
        return self._soup(html).select_one(selector)

    def extract(
        self,
        html: str,
        selectors: dict[str, str],
        transforms: dict[str, Callable[[str], str]] | None = None,
    ) -> dict[str, str | None]:
        """Extract named fields from HTML using CSS selectors.

        Returns a dict with field names as keys. Missing fields are None.
        """
        soup = self._soup(html)
        result: dict[str, str | None] = {}
        for field_name, selector in selectors.items():
            element = soup.select_one(selector)
            if element:
                value = element.get_text(strip=True)
                if transforms and field_name in transforms:
                    value = transforms[field_name](value)
                result[field_name] = value
            else:
                result[field_name] = None
        return result

    def extract_list(
        self,
        html: str,
        selector: str,
        attr: str | None = None,
    ) -> list[str]:
        """Extract a list of values from HTML using a CSS selector.

        If attr is provided, extracts that attribute from each element.
        Otherwise extracts text content.
        """
        soup = self._soup(html)
        elements = soup.select(selector)
        if attr:
            return [el[attr] for el in elements if el.has_attr(attr)]
        return [el.get_text(strip=True) for el in elements]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_parser.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/parser.py tests/test_parser.py
git commit -m "feat: add CSS-selector-driven HTML parser"
```

---

### Task 3: Browser Abstraction

**Files:**
- Create: `src/core/browser.py`
- Create: `tests/test_browser.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_browser.py
import pytest
import httpx
from src.core.browser import HttpClient, BrowserClient


class TestHttpClient:
    async def test_get_returns_response(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com", text="<html>hello</html>")
        client = HttpClient(timeout=10, rate_limit_delay=0)
        response = await client.get("https://example.com")
        assert response.status_code == 200
        assert response.text == "<html>hello</html>"

    async def test_get_with_headers(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com", text="ok")
        client = HttpClient(
            timeout=10,
            rate_limit_delay=0,
            headers={"User-Agent": "TestBot/1.0"},
        )
        response = await client.get("https://example.com")
        request = httpx_mock.get_request()
        assert request.headers["User-Agent"] == "TestBot/1.0"

    async def test_post_form(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/search", text="<html>results</html>")
        client = HttpClient(timeout=10, rate_limit_delay=0)
        response = await client.post(
            "https://example.com/search",
            data={"date_from": "01/01/2024", "date_to": "14/01/2024"},
        )
        assert response.status_code == 200
        request = httpx_mock.get_request()
        assert b"date_from" in request.content

    async def test_get_html(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com", text="<html><body>test</body></html>")
        client = HttpClient(timeout=10, rate_limit_delay=0)
        html = await client.get_html("https://example.com")
        assert "<body>test</body>" in html

    async def test_context_manager(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com", text="ok")
        async with HttpClient(timeout=10, rate_limit_delay=0) as client:
            response = await client.get("https://example.com")
            assert response.status_code == 200


class TestBrowserClient:
    def test_browser_client_interface_exists(self):
        """BrowserClient wraps Playwright — just verify it can be imported and has the interface."""
        assert hasattr(BrowserClient, "get")
        assert hasattr(BrowserClient, "post")
        assert hasattr(BrowserClient, "get_html")
        assert hasattr(BrowserClient, "__aenter__")
        assert hasattr(BrowserClient, "__aexit__")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_browser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.core.browser'`

- [ ] **Step 3: Write the browser implementation**

```python
# src/core/browser.py
import asyncio
from typing import Any

import httpx


class HttpClient:
    """Async HTTP client using httpx. Default client for server-rendered pages."""

    def __init__(
        self,
        timeout: float = 30,
        rate_limit_delay: float = 1.0,
        headers: dict[str, str] | None = None,
    ):
        default_headers = {
            "User-Agent": "UKPlanningScraper/2.0 (+https://github.com)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.5",
        }
        if headers:
            default_headers.update(headers)
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=default_headers,
            follow_redirects=True,
        )
        self._rate_limit_delay = rate_limit_delay

    async def _rate_limit(self) -> None:
        if self._rate_limit_delay > 0:
            await asyncio.sleep(self._rate_limit_delay)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        await self._rate_limit()
        return await self._client.get(url, **kwargs)

    async def post(self, url: str, data: dict | None = None, **kwargs: Any) -> httpx.Response:
        await self._rate_limit()
        return await self._client.post(url, data=data, **kwargs)

    async def get_html(self, url: str) -> str:
        response = await self.get(url)
        response.raise_for_status()
        return response.text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()


class BrowserClient:
    """Headless browser client using Playwright. For JS-heavy council sites."""

    def __init__(
        self,
        timeout: float = 30,
        rate_limit_delay: float = 1.0,
        headers: dict[str, str] | None = None,
    ):
        self._timeout = timeout
        self._rate_limit_delay = rate_limit_delay
        self._headers = headers or {}
        self._browser = None
        self._context = None
        self._page = None

    async def _rate_limit(self) -> None:
        if self._rate_limit_delay > 0:
            await asyncio.sleep(self._rate_limit_delay)

    async def _ensure_browser(self) -> None:
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
            self._context = await self._browser.new_context(
                extra_http_headers=self._headers,
            )
            self._page = await self._context.new_page()

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        await self._rate_limit()
        await self._ensure_browser()
        response = await self._page.goto(url, timeout=self._timeout * 1000)
        content = await self._page.content()
        return httpx.Response(
            status_code=response.status if response else 200,
            text=content,
            request=httpx.Request("GET", url),
        )

    async def post(self, url: str, data: dict | None = None, **kwargs: Any) -> httpx.Response:
        await self._rate_limit()
        await self._ensure_browser()
        if data:
            for field_name, value in data.items():
                locator = self._page.locator(f'[name="{field_name}"]')
                if await locator.count() > 0:
                    await locator.fill(str(value))
            await self._page.locator('input[type="submit"], button[type="submit"]').first.click()
            await self._page.wait_for_load_state("networkidle")
        content = await self._page.content()
        return httpx.Response(
            status_code=200,
            text=content,
            request=httpx.Request("POST", url),
        )

    async def get_html(self, url: str) -> str:
        response = await self.get(url)
        return response.text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_pw") and self._pw:
            await self._pw.stop()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_browser.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/browser.py tests/test_browser.py
git commit -m "feat: add httpx and playwright browser abstraction"
```

---

### Task 4: Council Config System

**Files:**
- Create: `src/core/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import pytest
import tempfile
import os
from pathlib import Path
from src.core.config import CouncilConfig, load_council_config, load_all_councils


SAMPLE_YAML = """
name: Hart
authority_code: hart
platform: idox
base_url: "https://publicaccess.hart.gov.uk/online-applications"
schedule: "0 3 * * *"
requires_js: false
selectors:
  reference: "th:-soup-contains('Reference') + td"
  address: "th:-soup-contains('Address') + td"
fields:
  date_received: date_validated
"""

SAMPLE_CUSTOM_YAML = """
name: Ashfield
authority_code: ashfield
platform: custom
scraper_class: "custom.ashfield.AshfieldScraper"
base_url: "https://www.ashfield.gov.uk/planning"
schedule: "0 3 * * 1"
requires_js: false
"""

SAMPLE_MINIMAL_YAML = """
name: Bexley
authority_code: bexley
platform: idox
base_url: "https://pa.bexley.gov.uk/online-applications"
"""


class TestCouncilConfig:
    def test_load_full_config(self, tmp_path):
        config_file = tmp_path / "hart.yml"
        config_file.write_text(SAMPLE_YAML)
        config = load_council_config(config_file)
        assert config.name == "Hart"
        assert config.authority_code == "hart"
        assert config.platform == "idox"
        assert config.base_url == "https://publicaccess.hart.gov.uk/online-applications"
        assert config.schedule == "0 3 * * *"
        assert config.requires_js is False
        assert config.selectors["reference"] == "th:-soup-contains('Reference') + td"
        assert config.fields["date_received"] == "date_validated"

    def test_load_custom_config(self, tmp_path):
        config_file = tmp_path / "ashfield.yml"
        config_file.write_text(SAMPLE_CUSTOM_YAML)
        config = load_council_config(config_file)
        assert config.platform == "custom"
        assert config.scraper_class == "custom.ashfield.AshfieldScraper"

    def test_load_minimal_config_defaults(self, tmp_path):
        config_file = tmp_path / "bexley.yml"
        config_file.write_text(SAMPLE_MINIMAL_YAML)
        config = load_council_config(config_file)
        assert config.schedule == "0 3 * * *"
        assert config.requires_js is False
        assert config.selectors == {}
        assert config.fields == {}
        assert config.scraper_class is None

    def test_load_all_councils(self, tmp_path):
        (tmp_path / "hart.yml").write_text(SAMPLE_YAML)
        (tmp_path / "ashfield.yml").write_text(SAMPLE_CUSTOM_YAML)
        (tmp_path / "not_yaml.txt").write_text("ignore me")
        configs = load_all_councils(tmp_path)
        assert len(configs) == 2
        codes = {c.authority_code for c in configs}
        assert codes == {"hart", "ashfield"}

    def test_invalid_config_raises(self, tmp_path):
        config_file = tmp_path / "bad.yml"
        config_file.write_text("name: Bad\n")  # missing required fields
        with pytest.raises(Exception):
            load_council_config(config_file)

    def test_duplicate_authority_code_detected(self, tmp_path):
        (tmp_path / "hart1.yml").write_text(SAMPLE_YAML)
        (tmp_path / "hart2.yml").write_text(SAMPLE_YAML)
        with pytest.raises(ValueError, match="Duplicate authority_code"):
            load_all_councils(tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.core.config'`

- [ ] **Step 3: Write the config implementation**

```python
# src/core/config.py
from pathlib import Path

import yaml
from pydantic import BaseModel


class CouncilConfig(BaseModel):
    """Configuration for a single council scraper."""

    name: str
    authority_code: str
    platform: str
    base_url: str
    schedule: str = "0 3 * * *"
    requires_js: bool = False
    selectors: dict[str, str] = {}
    fields: dict[str, str] = {}
    scraper_class: str | None = None
    variant: str | None = None
    rate_limit_delay: float = 1.0
    batch_size_days: int = 14


def load_council_config(path: Path) -> CouncilConfig:
    """Load a single council config from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return CouncilConfig(**data)


def load_all_councils(directory: Path) -> list[CouncilConfig]:
    """Load all council configs from a directory of YAML files."""
    configs: list[CouncilConfig] = []
    seen_codes: dict[str, Path] = {}
    for path in sorted(directory.iterdir()):
        if path.suffix not in (".yml", ".yaml"):
            continue
        config = load_council_config(path)
        if config.authority_code in seen_codes:
            raise ValueError(
                f"Duplicate authority_code '{config.authority_code}' "
                f"in {path} and {seen_codes[config.authority_code]}"
            )
        seen_codes[config.authority_code] = path
        configs.append(config)
    return configs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/config.py tests/test_config.py
git commit -m "feat: add council YAML config system with pydantic validation"
```

---

### Task 5: Database Models & Migrations

**Files:**
- Create: `src/core/database.py`
- Create: `src/core/models.py`
- Create: `tests/conftest.py`
- Create: `tests/test_models.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`

- [ ] **Step 1: Write conftest.py with shared test fixtures**

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.core.models import Base


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_models.py
import pytest
from datetime import date, datetime, timezone
from sqlalchemy import select
from src.core.models import Council, Application, ScrapeRun


class TestCouncilModel:
    def test_create_council(self, db_session):
        council = Council(
            name="Hart",
            authority_code="hart",
            platform="idox",
            base_url="https://publicaccess.hart.gov.uk/online-applications",
            schedule_cron="0 3 * * *",
            enabled=True,
        )
        db_session.add(council)
        db_session.commit()
        result = db_session.execute(select(Council)).scalar_one()
        assert result.name == "Hart"
        assert result.authority_code == "hart"
        assert result.enabled is True

    def test_council_authority_code_unique(self, db_session):
        c1 = Council(name="Hart", authority_code="hart", platform="idox", base_url="https://example.com")
        c2 = Council(name="Hart2", authority_code="hart", platform="idox", base_url="https://example2.com")
        db_session.add(c1)
        db_session.commit()
        db_session.add(c2)
        with pytest.raises(Exception):
            db_session.commit()


class TestApplicationModel:
    def test_create_application(self, db_session):
        council = Council(name="Hart", authority_code="hart", platform="idox", base_url="https://example.com")
        db_session.add(council)
        db_session.commit()
        app = Application(
            council_id=council.id,
            reference="24/01234/FUL",
            url="https://example.com/app/123",
            address="123 High Street",
            description="Erection of new dwelling",
            application_type="Full",
            status="Pending",
            date_received=date(2024, 1, 15),
        )
        db_session.add(app)
        db_session.commit()
        result = db_session.execute(select(Application)).scalar_one()
        assert result.reference == "24/01234/FUL"
        assert result.council_id == council.id
        assert result.first_scraped_at is not None

    def test_application_unique_per_council(self, db_session):
        council = Council(name="Hart", authority_code="hart", platform="idox", base_url="https://example.com")
        db_session.add(council)
        db_session.commit()
        a1 = Application(council_id=council.id, reference="24/01234/FUL", address="addr1", description="desc1")
        a2 = Application(council_id=council.id, reference="24/01234/FUL", address="addr2", description="desc2")
        db_session.add(a1)
        db_session.commit()
        db_session.add(a2)
        with pytest.raises(Exception):
            db_session.commit()

    def test_application_raw_data_jsonb(self, db_session):
        council = Council(name="Hart", authority_code="hart", platform="idox", base_url="https://example.com")
        db_session.add(council)
        db_session.commit()
        app = Application(
            council_id=council.id,
            reference="24/01234/FUL",
            address="123 High Street",
            description="Test",
            raw_data={"extra_field": "value", "nested": {"key": "val"}},
        )
        db_session.add(app)
        db_session.commit()
        result = db_session.execute(select(Application)).scalar_one()
        assert result.raw_data["extra_field"] == "value"
        assert result.raw_data["nested"]["key"] == "val"


class TestScrapeRunModel:
    def test_create_scrape_run(self, db_session):
        council = Council(name="Hart", authority_code="hart", platform="idox", base_url="https://example.com")
        db_session.add(council)
        db_session.commit()
        run = ScrapeRun(
            council_id=council.id,
            status="success",
            applications_found=15,
            applications_updated=3,
            date_range_from=date(2024, 1, 1),
            date_range_to=date(2024, 1, 14),
        )
        db_session.add(run)
        db_session.commit()
        result = db_session.execute(select(ScrapeRun)).scalar_one()
        assert result.status == "success"
        assert result.applications_found == 15
        assert result.started_at is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.core.models'`

- [ ] **Step 4: Write the models implementation**

```python
# src/core/models.py
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Council(Base):
    __tablename__ = "councils"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    authority_code: Mapped[str] = mapped_column(String(100), unique=True)
    platform: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str] = mapped_column(Text)
    schedule_cron: Mapped[str] = mapped_column(String(50), default="0 3 * * *")
    requires_js: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    applications: Mapped[list["Application"]] = relationship(back_populates="council")
    scrape_runs: Mapped[list["ScrapeRun"]] = relationship(back_populates="council")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("council_id", "reference", name="uq_council_reference"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    council_id: Mapped[int] = mapped_column(ForeignKey("councils.id"))
    reference: Mapped[str] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    application_type: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(100))
    decision: Mapped[str | None] = mapped_column(String(255))
    date_received: Mapped[date | None] = mapped_column(Date)
    date_validated: Mapped[date | None] = mapped_column(Date)
    ward: Mapped[str | None] = mapped_column(String(255))
    parish: Mapped[str | None] = mapped_column(String(255))
    applicant_name: Mapped[str | None] = mapped_column(String(255))
    case_officer: Mapped[str | None] = mapped_column(String(255))
    first_scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    raw_data: Mapped[dict | None] = mapped_column(JSON)

    council: Mapped["Council"] = relationship(back_populates="applications")


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    council_id: Mapped[int] = mapped_column(ForeignKey("councils.id"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50))
    applications_found: Mapped[int] = mapped_column(Integer, default=0)
    applications_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    date_range_from: Mapped[date | None] = mapped_column(Date)
    date_range_to: Mapped[date | None] = mapped_column(Date)

    council: Mapped["Council"] = relationship(back_populates="scrape_runs")
```

- [ ] **Step 5: Write the database connection module**

```python
# src/core/database.py
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ukplanning:devpassword@localhost:5432/ukplanning",
)


def get_engine(url: str | None = None):
    return create_engine(url or DATABASE_URL)


def get_session_factory(engine=None):
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Set up Alembic**

Create `alembic.ini`:

```ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql://ukplanning:devpassword@localhost:5432/ukplanning

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `migrations/env.py`:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.core.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Create `migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 8: Commit**

```bash
git add src/core/models.py src/core/database.py tests/conftest.py tests/test_models.py alembic.ini migrations/env.py migrations/script.py.mako
git commit -m "feat: add SQLAlchemy models and Alembic migration setup"
```

---

### Task 6: Abstract Base Scraper & Data Types

**Files:**
- Create: `src/core/scraper.py`
- Create: `tests/test_scraper.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scraper.py
import pytest
from datetime import date
from src.core.scraper import (
    ApplicationSummary,
    ApplicationDetail,
    ScrapeResult,
    BaseScraper,
)
from src.core.config import CouncilConfig


DUMMY_CONFIG = CouncilConfig(
    name="TestCouncil",
    authority_code="test",
    platform="test_platform",
    base_url="https://example.com",
)


class TestDataTypes:
    def test_application_summary(self):
        summary = ApplicationSummary(uid="24/001", url="https://example.com/app/1")
        assert summary.uid == "24/001"
        assert summary.url == "https://example.com/app/1"

    def test_application_detail(self):
        detail = ApplicationDetail(
            reference="24/001",
            address="123 High Street",
            description="New dwelling",
            url="https://example.com/app/1",
            raw_data={"extra": "field"},
        )
        assert detail.reference == "24/001"
        assert detail.raw_data["extra"] == "field"

    def test_application_detail_optional_fields(self):
        detail = ApplicationDetail(reference="24/001", address="addr", description="desc")
        assert detail.application_type is None
        assert detail.ward is None
        assert detail.raw_data == {}

    def test_scrape_result_success(self):
        result = ScrapeResult(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 14),
            applications=[
                ApplicationDetail(reference="24/001", address="addr", description="desc"),
            ],
        )
        assert result.is_success is True
        assert result.error is None
        assert len(result.applications) == 1

    def test_scrape_result_failure(self):
        result = ScrapeResult(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 14),
            applications=[],
            error="Connection timeout",
        )
        assert result.is_success is False


class TestBaseScraper:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseScraper(config=DUMMY_CONFIG)

    def test_subclass_must_implement_gather_ids(self):
        class BadScraper(BaseScraper):
            pass

        with pytest.raises(TypeError):
            BadScraper(config=DUMMY_CONFIG)

    def test_subclass_with_methods_can_instantiate(self):
        class GoodScraper(BaseScraper):
            async def gather_ids(self, date_from, date_to):
                return []

            async def fetch_detail(self, application):
                return ApplicationDetail(reference="x", address="x", description="x")

        scraper = GoodScraper(config=DUMMY_CONFIG)
        assert scraper.config.authority_code == "test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scraper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.core.scraper'`

- [ ] **Step 3: Write the scraper base implementation**

```python
# src/core/scraper.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

from src.core.config import CouncilConfig


@dataclass
class ApplicationSummary:
    """Minimal application data from search results."""

    uid: str
    url: str | None = None


@dataclass
class ApplicationDetail:
    """Full application data from detail pages."""

    reference: str
    address: str
    description: str
    url: str | None = None
    application_type: str | None = None
    status: str | None = None
    decision: str | None = None
    date_received: date | None = None
    date_validated: date | None = None
    ward: str | None = None
    parish: str | None = None
    applicant_name: str | None = None
    case_officer: str | None = None
    raw_data: dict = field(default_factory=dict)


@dataclass
class ScrapeResult:
    """Result of a scraping run."""

    date_from: date
    date_to: date
    applications: list[ApplicationDetail] = field(default_factory=list)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.error is None


class BaseScraper(ABC):
    """Abstract base for all platform and custom scrapers."""

    def __init__(self, config: CouncilConfig):
        self.config = config

    @abstractmethod
    async def gather_ids(self, date_from: date, date_to: date) -> list[ApplicationSummary]:
        """Discover application IDs/URLs in a date range."""

    @abstractmethod
    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        """Fetch full details for a single application."""

    async def scrape(self, date_from: date, date_to: date) -> ScrapeResult:
        """Full pipeline: gather IDs then fetch details for each."""
        try:
            summaries = await self.gather_ids(date_from, date_to)
            details = []
            for summary in summaries:
                detail = await self.fetch_detail(summary)
                details.append(detail)
            return ScrapeResult(date_from=date_from, date_to=date_to, applications=details)
        except Exception as e:
            return ScrapeResult(date_from=date_from, date_to=date_to, error=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scraper.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/scraper.py tests/test_scraper.py
git commit -m "feat: add abstract base scraper and data types"
```

---

### Task 7: Integration Smoke Test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test that wires everything together**

```python
# tests/test_integration.py
import pytest
from datetime import date
from pathlib import Path
from sqlalchemy import select

from src.core.parser import PageParser
from src.core.browser import HttpClient
from src.core.config import CouncilConfig, load_council_config
from src.core.scraper import ApplicationSummary, ApplicationDetail, BaseScraper, ScrapeResult
from src.core.models import Council, Application, ScrapeRun


SAMPLE_CONFIG_YAML = """
name: TestCouncil
authority_code: test_council
platform: idox
base_url: "https://example.com/planning"
schedule: "0 3 * * *"
selectors:
  reference: "th:-soup-contains('Reference') + td"
  address: "th:-soup-contains('Address') + td"
  description: "th:-soup-contains('Proposal') + td"
"""


class FakeScraper(BaseScraper):
    """Concrete scraper for testing the full flow."""

    async def gather_ids(self, date_from, date_to):
        return [
            ApplicationSummary(uid="TEST/001", url="https://example.com/app/1"),
            ApplicationSummary(uid="TEST/002", url="https://example.com/app/2"),
        ]

    async def fetch_detail(self, application):
        return ApplicationDetail(
            reference=application.uid,
            address="123 Test Street",
            description="Test application",
            url=application.url,
        )


class TestIntegration:
    def test_config_to_scraper_flow(self, tmp_path):
        config_file = tmp_path / "test.yml"
        config_file.write_text(SAMPLE_CONFIG_YAML)
        config = load_council_config(config_file)
        scraper = FakeScraper(config=config)
        assert scraper.config.name == "TestCouncil"

    async def test_scraper_full_pipeline(self):
        config = CouncilConfig(
            name="TestCouncil",
            authority_code="test",
            platform="idox",
            base_url="https://example.com",
        )
        scraper = FakeScraper(config=config)
        result = await scraper.scrape(date(2024, 1, 1), date(2024, 1, 14))
        assert result.is_success
        assert len(result.applications) == 2
        assert result.applications[0].reference == "TEST/001"

    def test_parser_extracts_from_html(self):
        parser = PageParser()
        html = """
        <table>
          <tr><th>Reference</th><td>24/001</td></tr>
          <tr><th>Address</th><td>123 High St</td></tr>
          <tr><th>Proposal</th><td>New house</td></tr>
        </table>
        """
        selectors = {
            "reference": "th:-soup-contains('Reference') + td",
            "address": "th:-soup-contains('Address') + td",
            "description": "th:-soup-contains('Proposal') + td",
        }
        result = parser.extract(html, selectors)
        assert result["reference"] == "24/001"

    def test_scrape_result_to_db_model(self, db_session):
        council = Council(
            name="TestCouncil",
            authority_code="test",
            platform="idox",
            base_url="https://example.com",
        )
        db_session.add(council)
        db_session.commit()

        detail = ApplicationDetail(
            reference="24/001",
            address="123 High St",
            description="New house",
            raw_data={"extra": "data"},
        )
        app = Application(
            council_id=council.id,
            reference=detail.reference,
            address=detail.address,
            description=detail.description,
            raw_data=detail.raw_data,
        )
        db_session.add(app)
        db_session.commit()

        result = db_session.execute(select(Application)).scalar_one()
        assert result.reference == "24/001"
        assert result.council_id == council.id
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_integration.py -v`
Expected: All 4 tests PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS (parser: 8, browser: 6, config: 6, models: 6, scraper: 7, integration: 4 = 37 total)

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "feat: add integration smoke tests for core infrastructure"
```

---

## Summary

After completing this plan you will have:

- A modern Python 3.12+ project with all dependencies
- A CSS-selector-driven HTML parser
- An HTTP client abstraction (httpx default, Playwright for JS sites)
- A YAML-based council config system with Pydantic validation
- SQLAlchemy models for councils, applications, and scrape runs
- An abstract base scraper class with data types
- Alembic migration infrastructure
- Docker Compose for Postgres
- 37 passing tests

**Next plan:** Plan 2 — Idox Platform Scraper (builds on this foundation)
