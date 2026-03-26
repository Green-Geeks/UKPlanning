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
