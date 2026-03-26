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
