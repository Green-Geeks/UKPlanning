import asyncio
import logging
import random
import ssl
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Per-domain semaphores to prevent hammering shared infrastructure
_domain_semaphores: Dict[str, asyncio.Semaphore] = {}
_domain_lock = asyncio.Lock()

BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
]


async def _get_domain_semaphore(url: str, max_concurrent: int = 2) -> asyncio.Semaphore:
    """Get or create a per-domain semaphore to limit concurrent requests."""
    domain = urlparse(url).netloc
    async with _domain_lock:
        if domain not in _domain_semaphores:
            _domain_semaphores[domain] = asyncio.Semaphore(max_concurrent)
        return _domain_semaphores[domain]


class HttpClient:
    """Async HTTP client using httpx. Default client for server-rendered pages."""

    def __init__(
        self,
        timeout: float = 30,
        rate_limit_delay: float = 2.0,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 5,
    ):
        default_headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        if headers:
            default_headers.update(headers)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=default_headers,
            follow_redirects=True,
            verify=ctx,
        )
        self._rate_limit_delay = rate_limit_delay
        self._max_retries = max_retries

    async def _rate_limit(self) -> None:
        if self._rate_limit_delay > 0:
            jitter = random.uniform(0.5, 1.5)
            await asyncio.sleep(self._rate_limit_delay * jitter)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        sem = await _get_domain_semaphore(url)
        async with sem:
            await self._rate_limit()
            return await self._retry_on_error(self._client.get, url, **kwargs)

    async def post(self, url: str, data: Optional[Dict] = None, **kwargs: Any) -> httpx.Response:
        sem = await _get_domain_semaphore(url)
        async with sem:
            await self._rate_limit()
            return await self._retry_on_error(self._client.post, url, data=data, **kwargs)

    async def get_html(self, url: str) -> str:
        response = await self.get(url)
        response.raise_for_status()
        return response.text

    async def _retry_on_error(self, method, *args, **kwargs) -> httpx.Response:
        last_exc = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await method(*args, **kwargs)
                if response.status_code == 429:
                    if attempt == self._max_retries:
                        return response
                    retry_after = response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        wait = min(int(retry_after), 120)
                    else:
                        wait = min(2 ** (attempt + 2), 120)
                    jitter = random.uniform(0.5, 1.5)
                    logger.info("429 on attempt %d, waiting %.0fs", attempt + 1, wait * jitter)
                    await asyncio.sleep(wait * jitter)
                    continue
                if response.status_code >= 500 and attempt < self._max_retries:
                    wait = min(2 ** (attempt + 1), 60)
                    logger.info("Server %d on attempt %d, retrying in %ds", response.status_code, attempt + 1, wait)
                    await asyncio.sleep(wait)
                    continue
                return response
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_exc = e
                if attempt == self._max_retries:
                    raise
                wait = min(2 ** (attempt + 1), 60)
                logger.info("Connection error on attempt %d: %s, retrying in %ds", attempt + 1, type(e).__name__, wait)
                await asyncio.sleep(wait)
        raise last_exc

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
