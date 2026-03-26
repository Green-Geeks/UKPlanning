# UKPlanning Scraper Rewrite — Design Spec

## Overview

Rewrite of the legacy Python 2.7 UKPlanning scraper into a modern Python 3.12+ system that scrapes planning applications from ~430 UK council portals, stores them in PostgreSQL, and surfaces them via a web dashboard.

**Goal:** Build a comprehensive, maintainable database of UK planning applications to identify and fight applications related to animal slaughter facilities.

**Reference:** Based on the open-source work from https://www.planit.org.uk/ (~2017 snapshot). The original repo covers 433 councils across ~15 platform types, with Idox being dominant (57%).

## Tech Stack

- **Language:** Python 3.12+
- **HTTP:** `httpx` (async) as default, `playwright` for JS-heavy sites
- **Parsing:** `beautifulsoup4` + `lxml` with CSS selectors
- **Database:** PostgreSQL via `sqlalchemy` + `alembic`
- **Scheduling:** `apscheduler`
- **Dashboard:** `fastapi` + `jinja2`
- **Config validation:** `pydantic`
- **Deployment:** Docker Compose on a dedicated cloud server

## Project Structure

```
ukplanning/
├── src/
│   ├── platforms/          # Base scraper per platform (idox.py, swiftlg.py, etc.)
│   ├── variants/           # Subclasses for platform deviations
│   ├── custom/             # Fully custom one-off council scrapers
│   ├── core/
│   │   ├── scraper.py      # Abstract base scraper class
│   │   ├── browser.py      # httpx client + Playwright wrapper
│   │   ├── parser.py       # BS4/CSS selector extraction engine
│   │   └── models.py       # SQLAlchemy models
│   ├── scheduler/
│   │   ├── orchestrator.py # Runs scrapers per council on schedule
│   │   └── health.py       # Monitors scraper health, disables broken ones
│   ├── dashboard/
│   │   ├── app.py          # FastAPI web UI
│   │   └── templates/      # Jinja2 templates
│   └── config/
│       └── councils/       # One YAML file per council
├── migrations/             # Alembic DB migrations
├── tests/
├── pyproject.toml
└── docker-compose.yml
```

## Architecture

### Platform-First with Layered Overrides

Councils are not individual scrapers. Instead, each council is a **config entry** that points to a **platform scraper**. The platform scraper defines the default scraping flow and selectors. Councils can override selectors and field mappings without writing Python.

**Override hierarchy:**
1. Platform base class — default selectors, navigation flow, pagination
2. Variant subclass (optional) — overrides for groups of councils with shared deviations
3. Council YAML config — per-council selector and field overrides

**Estimated breakdown:**
- ~10-15 platform base classes covering major systems
- Variant subclasses where groups of councils share deviations (e.g. IdoxScots, IdoxNI)
- ~67 fully custom scrapers for one-off council portals

### Council Configuration

Each council is a YAML file:

```yaml
# config/councils/hart.yml
name: Hart
authority_code: hart
platform: idox
base_url: "https://publicaccess.hart.gov.uk/online-applications"
schedule: "0 3 * * *"  # daily at 03:00
selectors:
  search_results: "ul#searchresults li"
  reference: "th:contains('Reference') + td"
fields:
  date_received: date_validated
requires_js: false
```

Custom councils point to a scraper class:

```yaml
name: Ashfield
authority_code: ashfield
platform: custom
scraper_class: "custom.ashfield.AshfieldScraper"
schedule: "0 3 * * 1"  # weekly on Monday at 03:00
```

### Scraper Interface

All scrapers implement:

```python
class BaseScraper(ABC):
    async def gather_ids(self, date_from, date_to) -> list[ApplicationSummary]:
        """Discover application IDs/URLs in a date range"""

    async def fetch_detail(self, application: ApplicationSummary) -> ApplicationDetail:
        """Fetch full details for a single application"""

    async def scrape(self, date_from, date_to) -> ScrapeResult:
        """Full pipeline: gather IDs then fetch details"""
```

Platform scrapers inherit and implement the scraping flow (navigation, form submission, pagination, data extraction). The parser is config-driven — given HTML and a selector map, it extracts all fields.

### Browser Abstraction

Two HTTP client implementations behind a common interface:

- `HttpClient` — async `httpx` client (default, lightweight)
- `PlaywrightClient` — headless browser for JS-heavy sites

The council config's `requires_js` flag determines which client is used. Both expose the same interface so scraper code is client-agnostic.

**Rate limiting:** configurable delay between requests per council to be a good net citizen.

## Database Schema

### councils

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| name | text | "Hart" |
| authority_code | text | unique, "hart" |
| platform | text | "idox" |
| base_url | text | |
| schedule_cron | text | cron expression, e.g. "0 3 * * *" for daily at 03:00 |
| requires_js | boolean | |
| enabled | boolean | |
| last_scraped_at | timestamp | |
| last_successful_at | timestamp | |

### applications

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| council_id | FK | |
| reference | text | unique per council, e.g. "24/01234/FUL" |
| url | text | |
| address | text | |
| description | text | |
| application_type | text | |
| status | text | Pending, Approved, Refused |
| decision | text | |
| date_received | date | |
| date_validated | date | |
| ward | text | |
| parish | text | |
| applicant_name | text | |
| case_officer | text | |
| first_scraped_at | timestamp | when we first found it |
| last_updated_at | timestamp | last detail refresh |
| raw_data | JSONB | full extracted fields, future-proofing |

### scrape_runs

| Column | Type | Notes |
|---|---|---|
| id | PK | |
| council_id | FK | |
| started_at | timestamp | |
| completed_at | timestamp | |
| status | text | success, partial, failed |
| applications_found | integer | |
| applications_updated | integer | |
| error_message | text | |
| date_range_from | date | |
| date_range_to | date | |

## Scheduler

- APScheduler with one job per council, each with its own interval from config
- Each job: `gather_ids` for the period since `last_scraped_at`, then `fetch_detail` for new/updated applications
- Results written to Postgres, `scrape_run` entry logged
- 3 consecutive failures auto-disables the council with a warning
- Staggered start times to avoid hitting all councils simultaneously

## Dashboard

FastAPI + Jinja2, no authentication (private server).

**Pages:**
1. **Search** — full-text search across application descriptions and addresses. Filter by council, date range, status
2. **Council overview** — all councils with scraper health (last run, success rate, total applications)
3. **Council detail** — applications for a specific council, scrape run history
4. **Application detail** — single application with all extracted fields

## Migration Strategy

1. **Extract council registry** — parse `scraper_list.csv` and old scraper source files to generate initial YAML configs (name, platform type, base URL)
2. **Verify URLs** — automated check which base URLs still respond
3. **Build platform scrapers in priority order:**
   - Idox first (covers ~250 councils)
   - PlanningExplorer (20 councils)
   - SwiftLG (21 councils)
   - Remaining platforms in descending council count
   - Custom scrapers last
4. **Validate against live sites** — per platform, test 3-4 councils, confirm extraction
5. **Iterate** — fix variants as they surface, add overrides to configs

**From the old codebase we keep:** council-to-platform mappings, URL patterns, knowledge of platform variants.

**From the old codebase we discard:** all Python 2 code, mechanize, scrapemark, BeautifulSoup v3, the class hierarchy.

**Realistic expectation:** not all 427 councils will work on day one. Some will have changed platforms or URLs. The system fails gracefully per-council and broken scrapers are fixed incrementally.

## Future Considerations

- **Document scraping** — download and index attached PDFs/plans per application. Deferred but the `raw_data` JSONB and the modular architecture support adding this later.
- **Authentication** — if the dashboard is ever exposed beyond the private server.
- **API** — FastAPI already provides this for free alongside the dashboard routes.
