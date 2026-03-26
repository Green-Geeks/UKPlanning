import asyncio
from typing import Any, Dict, Optional

import httpx


class HttpClient:
    """Async HTTP client using httpx. Default client for server-rendered pages."""

    def __init__(
        self,
        timeout: float = 30,
        rate_limit_delay: float = 1.0,
        headers: Optional[Dict[str, str]] = None,
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

    async def post(self, url: str, data: Optional[Dict] = None, **kwargs: Any) -> httpx.Response:
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
        headers: Optional[Dict[str, str]] = None,
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

    async def post(self, url: str, data: Optional[Dict] = None, **kwargs: Any) -> httpx.Response:
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
