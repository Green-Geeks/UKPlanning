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
