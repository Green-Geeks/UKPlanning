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
        mock_resp = MagicMock(text=empty_html, url="https://example.com/search.do?action=advanced", status_code=200)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.get_html = AsyncMock(return_value=empty_html)
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200, text=empty_html, headers={},
        ))
        scraper._client = mock_client

        await scraper.gather_ids(date(2024, 1, 1), date(2024, 1, 14))

        # Verify the posted date_to is 15th (14th + 1 day)
        call_args = mock_client.post.call_args
        form_data = call_args.kwargs.get("data") or call_args[1].get("data")
        if form_data is None:
            form_data = call_args[0][1] if len(call_args[0]) > 1 else {}
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

        # Should have made one POST per case prefix
        assert mock_client.post.call_count == 2


class TestIdoxCrumbScraper:
    def test_crumb_selectors_differ(self):
        """IdoxCrumbScraper uses different selectors for breadcrumb layout."""
        crumb_scraper = IdoxCrumbScraper(config=CRUMB_CONFIG)
        standard_scraper = IdoxScraper(config=CouncilConfig(
            name="Standard", authority_code="std", platform="idox", base_url="https://example.com",
        ))
        assert crumb_scraper._summary_selectors["reference"] != standard_scraper._summary_selectors["reference"]
        assert "caseNumber" in crumb_scraper._summary_selectors["reference"]
