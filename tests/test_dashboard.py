import pytest
from fastapi.testclient import TestClient
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


from datetime import date, datetime, timezone
from src.core.models import Council, Application, ScrapeRun


class TestSearchPage:
    def _seed_data(self, db_engine):
        Session = sessionmaker(bind=db_engine)
        session = Session()
        council = Council(
            name="Hart", authority_code="hart", platform="idox",
            base_url="https://example.com", enabled=True,
        )
        session.add(council)
        session.commit()
        for i in range(3):
            app = Application(
                council_id=council.id,
                reference=f"24/0000{i}/FUL",
                address=f"{i} High Street",
                description=f"Test application {i}" if i != 2 else "Proposed slaughterhouse facility",
            )
            session.add(app)
        session.commit()
        session.close()
        return council

    def test_search_with_results(self, client, db_engine):
        self._seed_data(db_engine)
        response = client.get("/search?q=slaughter")
        assert response.status_code == 200
        assert "slaughterhouse" in response.text

    def test_search_empty_query(self, client, db_engine):
        self._seed_data(db_engine)
        response = client.get("/search")
        assert response.status_code == 200
        assert "3 results" in response.text


class TestCouncilPages:
    def _seed_data(self, db_engine):
        Session = sessionmaker(bind=db_engine)
        session = Session()
        council = Council(
            name="Hart", authority_code="hart", platform="idox",
            base_url="https://example.com", enabled=True,
        )
        session.add(council)
        session.commit()
        run = ScrapeRun(
            council_id=council.id, status="success",
            applications_found=5, applications_updated=2,
        )
        session.add(run)
        session.commit()
        session.close()
        return council

    def test_council_detail_page(self, client, db_engine):
        self._seed_data(db_engine)
        response = client.get("/councils/hart")
        assert response.status_code == 200
        assert "Hart" in response.text
        assert "success" in response.text

    def test_council_not_found(self, client):
        response = client.get("/councils/nonexistent")
        assert response.status_code == 200
        assert "not found" in response.text.lower()


class TestApplicationPage:
    def _seed_data(self, db_engine):
        Session = sessionmaker(bind=db_engine)
        session = Session()
        council = Council(
            name="Hart", authority_code="hart", platform="idox",
            base_url="https://example.com", enabled=True,
        )
        session.add(council)
        session.commit()
        app = Application(
            council_id=council.id,
            reference="24/00001/FUL",
            address="123 High Street",
            description="New dwelling",
            application_type="Full",
            status="Pending",
            raw_data={"extra": "data"},
        )
        session.add(app)
        session.commit()
        app_id = app.id
        session.close()
        return app_id

    def test_application_detail_page(self, client, db_engine):
        app_id = self._seed_data(db_engine)
        response = client.get(f"/applications/{app_id}")
        assert response.status_code == 200
        assert "24/00001/FUL" in response.text
        assert "123 High Street" in response.text
        assert "New dwelling" in response.text

    def test_application_not_found(self, client):
        response = client.get("/applications/99999")
        assert response.status_code == 200
        assert "not found" in response.text.lower()
