# Plan 4: Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI web dashboard for browsing planning applications, searching by keyword, and monitoring scraper health across all councils.

**Architecture:** FastAPI with Jinja2 templates. Server-side rendered HTML (no frontend framework needed). Full-text search via PostgreSQL `ILIKE` queries (upgrade to tsvector later if needed). No auth — private server.

**Tech Stack:** FastAPI, Jinja2, uvicorn, SQLAlchemy (from Plan 1)

---

## File Structure

```
src/
├── dashboard/
│   ├── __init__.py
│   ├── app.py              # FastAPI app factory and routes
│   ├── dependencies.py     # DB session dependency
│   └── templates/
│       ├── base.html        # Shared layout
│       ├── search.html      # Search page with results
│       ├── councils.html    # Council overview list
│       ├── council.html     # Single council detail
│       └── application.html # Single application detail
tests/
├── test_dashboard.py
```

---

### Task 1: FastAPI App & Base Template

**Files:**
- Create: `src/dashboard/__init__.py`
- Create: `src/dashboard/dependencies.py`
- Create: `src/dashboard/app.py` (routes stub)
- Create: `src/dashboard/templates/base.html`
- Create: `tests/test_dashboard.py` (initial)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dashboard.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.models import Base
from src.dashboard.app import create_app
from src.dashboard.dependencies import get_db


@pytest.fixture
def test_app(db_engine):
    app = create_app()
    Session = sessionmaker(bind=db_engine)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


class TestDashboardBasic:
    def test_homepage_redirects_to_search(self, client):
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert "/search" in response.headers["location"]

    def test_search_page_loads(self, client):
        response = client.get("/search")
        assert response.status_code == 200
        assert "Search" in response.text

    def test_councils_page_loads(self, client):
        response = client.get("/councils")
        assert response.status_code == 200
        assert "Councils" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard.py -v`
Expected: FAIL

- [ ] **Step 3: Implement app factory and base template**

```python
# src/dashboard/__init__.py
# empty

# src/dashboard/dependencies.py
from src.core.database import get_engine
from sqlalchemy.orm import sessionmaker


def get_db():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
```

```python
# src/dashboard/app.py
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from src.core.models import Council, Application, ScrapeRun
from src.dashboard.dependencies import get_db

TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app() -> FastAPI:
    app = FastAPI(title="UK Planning Dashboard")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/")
    async def index():
        return RedirectResponse(url="/search")

    @app.get("/search")
    async def search(
        request: Request,
        q: str = "",
        council: str = "",
        page: int = 1,
        db: Session = Depends(get_db),
    ):
        per_page = 50
        offset = (page - 1) * per_page

        query = select(Application).join(Council)

        if q:
            query = query.where(
                Application.description.ilike(f"%{q}%")
                | Application.address.ilike(f"%{q}%")
            )
        if council:
            query = query.where(Council.authority_code == council)

        total = db.execute(
            select(func.count()).select_from(query.subquery())
        ).scalar()

        applications = db.execute(
            query.order_by(Application.first_scraped_at.desc())
            .offset(offset).limit(per_page)
        ).scalars().all()

        councils = db.execute(
            select(Council).order_by(Council.name)
        ).scalars().all()

        return templates.TemplateResponse("search.html", {
            "request": request,
            "applications": applications,
            "councils": councils,
            "q": q,
            "selected_council": council,
            "page": page,
            "total": total,
            "per_page": per_page,
        })

    @app.get("/councils")
    async def councils_list(
        request: Request,
        db: Session = Depends(get_db),
    ):
        councils = db.execute(
            select(Council).order_by(Council.name)
        ).scalars().all()

        stats = {}
        for c in councils:
            app_count = db.execute(
                select(func.count()).where(Application.council_id == c.id)
            ).scalar()
            last_run = db.execute(
                select(ScrapeRun)
                .where(ScrapeRun.council_id == c.id)
                .order_by(ScrapeRun.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            stats[c.id] = {
                "app_count": app_count,
                "last_run": last_run,
            }

        return templates.TemplateResponse("councils.html", {
            "request": request,
            "councils": councils,
            "stats": stats,
        })

    @app.get("/councils/{authority_code}")
    async def council_detail(
        request: Request,
        authority_code: str,
        page: int = 1,
        db: Session = Depends(get_db),
    ):
        council = db.execute(
            select(Council).where(Council.authority_code == authority_code)
        ).scalar_one_or_none()

        if not council:
            return templates.TemplateResponse("council.html", {
                "request": request, "council": None,
                "applications": [], "runs": [],
                "page": 1, "total": 0, "per_page": 50,
            })

        per_page = 50
        offset = (page - 1) * per_page

        total = db.execute(
            select(func.count()).where(Application.council_id == council.id)
        ).scalar()

        applications = db.execute(
            select(Application)
            .where(Application.council_id == council.id)
            .order_by(Application.first_scraped_at.desc())
            .offset(offset).limit(per_page)
        ).scalars().all()

        runs = db.execute(
            select(ScrapeRun)
            .where(ScrapeRun.council_id == council.id)
            .order_by(ScrapeRun.id.desc())
            .limit(20)
        ).scalars().all()

        return templates.TemplateResponse("council.html", {
            "request": request,
            "council": council,
            "applications": applications,
            "runs": runs,
            "page": page,
            "total": total,
            "per_page": per_page,
        })

    @app.get("/applications/{app_id}")
    async def application_detail(
        request: Request,
        app_id: int,
        db: Session = Depends(get_db),
    ):
        application = db.execute(
            select(Application).where(Application.id == app_id)
        ).scalar_one_or_none()

        council = None
        if application:
            council = db.execute(
                select(Council).where(Council.id == application.council_id)
            ).scalar_one_or_none()

        return templates.TemplateResponse("application.html", {
            "request": request,
            "application": application,
            "council": council,
        })

    return app
```

```html
<!-- src/dashboard/templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}UK Planning Dashboard{% endblock %}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #333; line-height: 1.6; }
        nav { background: #1a365d; color: white; padding: 1rem 2rem; display: flex; gap: 2rem; align-items: center; }
        nav a { color: white; text-decoration: none; font-weight: 500; }
        nav a:hover { text-decoration: underline; }
        nav .brand { font-size: 1.2rem; font-weight: 700; }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #e2e8f0; }
        th { background: #f7fafc; font-weight: 600; }
        tr:hover { background: #f7fafc; }
        a { color: #2b6cb0; }
        .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.85rem; font-weight: 500; }
        .badge-success { background: #c6f6d5; color: #22543d; }
        .badge-danger { background: #fed7d7; color: #742a2a; }
        .badge-warning { background: #fefcbf; color: #744210; }
        .badge-info { background: #bee3f8; color: #2a4365; }
        .search-form { display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }
        .search-form input[type="text"] { flex: 1; min-width: 200px; padding: 0.5rem 1rem; border: 1px solid #cbd5e0; border-radius: 4px; font-size: 1rem; }
        .search-form select { padding: 0.5rem; border: 1px solid #cbd5e0; border-radius: 4px; }
        .search-form button { padding: 0.5rem 1.5rem; background: #2b6cb0; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; }
        .search-form button:hover { background: #2c5282; }
        .pagination { margin: 2rem 0; display: flex; gap: 0.5rem; }
        .pagination a { padding: 0.5rem 1rem; border: 1px solid #cbd5e0; border-radius: 4px; text-decoration: none; }
        .pagination a.active { background: #2b6cb0; color: white; border-color: #2b6cb0; }
        .stat { font-size: 2rem; font-weight: 700; }
        .stat-label { font-size: 0.875rem; color: #718096; }
        .stats-row { display: flex; gap: 2rem; margin-bottom: 2rem; }
        .detail-grid { display: grid; grid-template-columns: 200px 1fr; gap: 0.5rem 1rem; }
        .detail-grid dt { font-weight: 600; color: #4a5568; }
        .detail-grid dd { margin: 0; }
        h1 { margin-bottom: 1rem; }
        h2 { margin: 1.5rem 0 0.75rem; }
    </style>
</head>
<body>
    <nav>
        <span class="brand">UK Planning</span>
        <a href="/search">Search</a>
        <a href="/councils">Councils</a>
    </nav>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
```

```html
<!-- src/dashboard/templates/search.html -->
{% extends "base.html" %}
{% block title %}Search - UK Planning Dashboard{% endblock %}
{% block content %}
<h1>Search Planning Applications</h1>
<form class="search-form" method="get" action="/search">
    <input type="text" name="q" value="{{ q }}" placeholder="Search descriptions and addresses...">
    <select name="council">
        <option value="">All Councils</option>
        {% for c in councils %}
        <option value="{{ c.authority_code }}" {% if c.authority_code == selected_council %}selected{% endif %}>{{ c.name }}</option>
        {% endfor %}
    </select>
    <button type="submit">Search</button>
</form>
<p>{{ total }} results found{% if q %} for "{{ q }}"{% endif %}</p>
<table>
    <thead>
        <tr><th>Reference</th><th>Address</th><th>Description</th><th>Status</th><th>Received</th></tr>
    </thead>
    <tbody>
    {% for app in applications %}
        <tr>
            <td><a href="/applications/{{ app.id }}">{{ app.reference }}</a></td>
            <td>{{ app.address or "" }}</td>
            <td>{{ app.description or "" }}</td>
            <td>{% if app.status %}<span class="badge badge-info">{{ app.status }}</span>{% endif %}</td>
            <td>{{ app.date_received or "" }}</td>
        </tr>
    {% endfor %}
    </tbody>
</table>
{% if total > per_page %}
<div class="pagination">
    {% if page > 1 %}<a href="/search?q={{ q }}&council={{ selected_council }}&page={{ page - 1 }}">Previous</a>{% endif %}
    <span>Page {{ page }} of {{ (total // per_page) + 1 }}</span>
    {% if page * per_page < total %}<a href="/search?q={{ q }}&council={{ selected_council }}&page={{ page + 1 }}">Next</a>{% endif %}
</div>
{% endif %}
{% endblock %}
```

```html
<!-- src/dashboard/templates/councils.html -->
{% extends "base.html" %}
{% block title %}Councils - UK Planning Dashboard{% endblock %}
{% block content %}
<h1>Councils</h1>
<table>
    <thead>
        <tr><th>Name</th><th>Platform</th><th>Applications</th><th>Last Run</th><th>Status</th></tr>
    </thead>
    <tbody>
    {% for c in councils %}
        <tr>
            <td><a href="/councils/{{ c.authority_code }}">{{ c.name }}</a></td>
            <td>{{ c.platform }}</td>
            <td>{{ stats[c.id].app_count }}</td>
            <td>{% if stats[c.id].last_run %}{{ stats[c.id].last_run.completed_at or "Running" }}{% else %}Never{% endif %}</td>
            <td>
                {% if not c.enabled %}<span class="badge badge-danger">Disabled</span>
                {% elif stats[c.id].last_run and stats[c.id].last_run.status == "failed" %}<span class="badge badge-warning">Failing</span>
                {% elif stats[c.id].last_run and stats[c.id].last_run.status == "success" %}<span class="badge badge-success">Healthy</span>
                {% else %}<span class="badge badge-info">Pending</span>{% endif %}
            </td>
        </tr>
    {% endfor %}
    </tbody>
</table>
{% endblock %}
```

```html
<!-- src/dashboard/templates/council.html -->
{% extends "base.html" %}
{% block title %}{{ council.name if council else "Not Found" }} - UK Planning Dashboard{% endblock %}
{% block content %}
{% if council %}
<h1>{{ council.name }}</h1>
<dl class="detail-grid">
    <dt>Platform</dt><dd>{{ council.platform }}</dd>
    <dt>Base URL</dt><dd><a href="{{ council.base_url }}" target="_blank">{{ council.base_url }}</a></dd>
    <dt>Schedule</dt><dd>{{ council.schedule_cron }}</dd>
    <dt>Status</dt><dd>{% if council.enabled %}<span class="badge badge-success">Enabled</span>{% else %}<span class="badge badge-danger">Disabled</span>{% endif %}</dd>
    <dt>Last Scraped</dt><dd>{{ council.last_scraped_at or "Never" }}</dd>
    <dt>Last Success</dt><dd>{{ council.last_successful_at or "Never" }}</dd>
</dl>

<h2>Recent Scrape Runs</h2>
<table>
    <thead><tr><th>Started</th><th>Status</th><th>Found</th><th>Updated</th><th>Error</th></tr></thead>
    <tbody>
    {% for run in runs %}
        <tr>
            <td>{{ run.started_at }}</td>
            <td><span class="badge badge-{{ 'success' if run.status == 'success' else 'danger' }}">{{ run.status }}</span></td>
            <td>{{ run.applications_found }}</td>
            <td>{{ run.applications_updated }}</td>
            <td>{{ run.error_message or "" }}</td>
        </tr>
    {% endfor %}
    </tbody>
</table>

<h2>Applications ({{ total }})</h2>
<table>
    <thead><tr><th>Reference</th><th>Address</th><th>Description</th><th>Status</th></tr></thead>
    <tbody>
    {% for app in applications %}
        <tr>
            <td><a href="/applications/{{ app.id }}">{{ app.reference }}</a></td>
            <td>{{ app.address or "" }}</td>
            <td>{{ app.description or "" }}</td>
            <td>{{ app.status or "" }}</td>
        </tr>
    {% endfor %}
    </tbody>
</table>
{% else %}
<h1>Council not found</h1>
{% endif %}
{% endblock %}
```

```html
<!-- src/dashboard/templates/application.html -->
{% extends "base.html" %}
{% block title %}{{ application.reference if application else "Not Found" }} - UK Planning Dashboard{% endblock %}
{% block content %}
{% if application %}
<h1>{{ application.reference }}</h1>
<p><a href="/councils/{{ council.authority_code }}">{{ council.name }}</a></p>
<dl class="detail-grid">
    <dt>Address</dt><dd>{{ application.address or "N/A" }}</dd>
    <dt>Description</dt><dd>{{ application.description or "N/A" }}</dd>
    <dt>Type</dt><dd>{{ application.application_type or "N/A" }}</dd>
    <dt>Status</dt><dd>{{ application.status or "N/A" }}</dd>
    <dt>Decision</dt><dd>{{ application.decision or "N/A" }}</dd>
    <dt>Date Received</dt><dd>{{ application.date_received or "N/A" }}</dd>
    <dt>Date Validated</dt><dd>{{ application.date_validated or "N/A" }}</dd>
    <dt>Ward</dt><dd>{{ application.ward or "N/A" }}</dd>
    <dt>Parish</dt><dd>{{ application.parish or "N/A" }}</dd>
    <dt>Applicant</dt><dd>{{ application.applicant_name or "N/A" }}</dd>
    <dt>Case Officer</dt><dd>{{ application.case_officer or "N/A" }}</dd>
    <dt>First Scraped</dt><dd>{{ application.first_scraped_at }}</dd>
    <dt>Last Updated</dt><dd>{{ application.last_updated_at }}</dd>
    {% if application.url %}
    <dt>Source</dt><dd><a href="{{ application.url }}" target="_blank">View on council website</a></dd>
    {% endif %}
</dl>
{% if application.raw_data %}
<h2>Raw Data</h2>
<pre style="background:#f7fafc;padding:1rem;border-radius:4px;overflow-x:auto;">{{ application.raw_data | tojson(indent=2) }}</pre>
{% endif %}
{% else %}
<h1>Application not found</h1>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/ tests/test_dashboard.py
git commit -m "feat: add FastAPI dashboard with search, councils, and application pages"
```

---

### Task 2: Dashboard Route Tests

**Files:**
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add comprehensive route tests**

Append to `tests/test_dashboard.py`:

```python
from datetime import date, datetime, timezone
from src.core.models import Council, Application, ScrapeRun


class TestSearchPage:
    def _seed_data(self, db_session):
        council = Council(
            name="Hart", authority_code="hart", platform="idox",
            base_url="https://example.com", enabled=True,
        )
        db_session.add(council)
        db_session.commit()
        for i in range(3):
            app = Application(
                council_id=council.id,
                reference=f"24/0000{i}/FUL",
                address=f"{i} High Street",
                description=f"Test application {i}" if i != 2 else "Proposed slaughterhouse facility",
            )
            db_session.add(app)
        db_session.commit()
        return council

    def test_search_with_results(self, client, db_engine):
        from src.core.models import Base
        Session = sessionmaker(bind=db_engine)
        session = Session()
        self._seed_data(session)
        session.close()

        response = client.get("/search?q=slaughter")
        assert response.status_code == 200
        assert "slaughterhouse" in response.text
        assert "1 results" in response.text or "1 result" in response.text

    def test_search_empty_query(self, client, db_engine):
        Session = sessionmaker(bind=db_engine)
        session = Session()
        self._seed_data(session)
        session.close()

        response = client.get("/search")
        assert response.status_code == 200
        assert "3 results" in response.text


class TestCouncilPages:
    def _seed_data(self, db_session):
        council = Council(
            name="Hart", authority_code="hart", platform="idox",
            base_url="https://example.com", enabled=True,
        )
        db_session.add(council)
        db_session.commit()
        run = ScrapeRun(
            council_id=council.id, status="success",
            applications_found=5, applications_updated=2,
        )
        db_session.add(run)
        db_session.commit()
        return council

    def test_council_detail_page(self, client, db_engine):
        Session = sessionmaker(bind=db_engine)
        session = Session()
        self._seed_data(session)
        session.close()

        response = client.get("/councils/hart")
        assert response.status_code == 200
        assert "Hart" in response.text
        assert "success" in response.text

    def test_council_not_found(self, client):
        response = client.get("/councils/nonexistent")
        assert response.status_code == 200
        assert "not found" in response.text.lower()


class TestApplicationPage:
    def _seed_data(self, db_session):
        council = Council(
            name="Hart", authority_code="hart", platform="idox",
            base_url="https://example.com", enabled=True,
        )
        db_session.add(council)
        db_session.commit()
        app = Application(
            council_id=council.id,
            reference="24/00001/FUL",
            address="123 High Street",
            description="New dwelling",
            application_type="Full",
            status="Pending",
            raw_data={"extra": "data"},
        )
        db_session.add(app)
        db_session.commit()
        return app

    def test_application_detail_page(self, client, db_engine):
        Session = sessionmaker(bind=db_engine)
        session = Session()
        app = self._seed_data(session)
        session.close()

        response = client.get(f"/applications/{app.id}")
        assert response.status_code == 200
        assert "24/00001/FUL" in response.text
        assert "123 High Street" in response.text
        assert "New dwelling" in response.text

    def test_application_not_found(self, client):
        response = client.get("/applications/99999")
        assert response.status_code == 200
        assert "not found" in response.text.lower()
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_dashboard.py -v`
Expected: All 8 tests PASS

- [ ] **Step 3: Run full suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard.py
git commit -m "feat: add comprehensive dashboard route tests"
```

---

## Summary

After completing this plan you will have:

- FastAPI dashboard with 4 pages: search, council list, council detail, application detail
- Full-text search across descriptions and addresses with council filter
- Pagination on all list views
- Scraper health status badges (Healthy/Failing/Disabled/Pending)
- Raw JSONB data display on application detail
- Clean CSS styling (no external dependencies)
- 8 dashboard tests + existing 73 = 81 total

**Next plan:** Plan 5 — Remaining Platform Scrapers
