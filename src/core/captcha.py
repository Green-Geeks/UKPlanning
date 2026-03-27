"""CAPTCHA bypass via visible browser session transfer.

Strategy:
1. Headless browser hits a page and detects CAPTCHA
2. Opens a visible (headed) browser to the same URL
3. User solves CAPTCHA manually (or it auto-passes in visible mode)
4. Captures cookies, localStorage, sessionStorage from the visible browser
5. Injects them into the headless browser session
6. Headless browser continues scraping with the authenticated session

Sessions are cached to disk so CAPTCHA only needs solving once per council.
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path(__file__).parent.parent.parent / ".captcha_sessions"


def _session_path(council_code: str) -> Path:
    SESSIONS_DIR.mkdir(exist_ok=True)
    return SESSIONS_DIR / f"{council_code}.json"


def load_session(council_code: str) -> Optional[dict]:
    """Load a cached session from disk."""
    path = _session_path(council_code)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        # Check if session is less than 24 hours old
        saved = datetime.fromisoformat(data.get("saved_at", "2000-01-01"))
        if (datetime.now() - saved).total_seconds() > 86400:
            logger.info(f"Session for {council_code} expired, needs re-solve")
            return None
        return data
    except Exception:
        return None


def save_session(council_code: str, session: dict):
    """Save a session to disk."""
    session["saved_at"] = datetime.now().isoformat()
    _session_path(council_code).write_text(json.dumps(session, indent=2))


async def detect_captcha(page: Page) -> bool:
    """Check if current page has a CAPTCHA challenge."""
    content = await page.content()
    indicators = [
        "recaptcha",
        "hcaptcha",
        "captcha",
        "g-recaptcha",
        "cf-turnstile",
    ]
    content_lower = content.lower()
    return any(indicator in content_lower for indicator in indicators)


async def capture_session(page: Page) -> dict:
    """Capture cookies, localStorage, and sessionStorage from a page."""
    cookies = await page.context.cookies()

    storage = await page.evaluate("""() => {
        let local = {};
        let session = {};
        try {
            for (let i = 0; i < localStorage.length; i++) {
                let k = localStorage.key(i);
                local[k] = localStorage.getItem(k);
            }
        } catch(e) {}
        try {
            for (let i = 0; i < sessionStorage.length; i++) {
                let k = sessionStorage.key(i);
                session[k] = sessionStorage.getItem(k);
            }
        } catch(e) {}
        return {localStorage: local, sessionStorage: session};
    }""")

    return {
        "cookies": cookies,
        "localStorage": storage.get("localStorage", {}),
        "sessionStorage": storage.get("sessionStorage", {}),
        "url": page.url,
    }


async def inject_session(page: Page, session: dict):
    """Inject saved cookies, localStorage, and sessionStorage into a page."""
    # Add cookies
    cookies = session.get("cookies", [])
    if cookies:
        await page.context.add_cookies(cookies)

    # Inject storage
    local_storage = session.get("localStorage", {})
    session_storage = session.get("sessionStorage", {})

    if local_storage or session_storage:
        await page.evaluate("""(data) => {
            if (data.localStorage) {
                for (let [k, v] of Object.entries(data.localStorage)) {
                    try { localStorage.setItem(k, v); } catch(e) {}
                }
            }
            if (data.sessionStorage) {
                for (let [k, v] of Object.entries(data.sessionStorage)) {
                    try { sessionStorage.setItem(k, v); } catch(e) {}
                }
            }
        }""", {"localStorage": local_storage, "sessionStorage": session_storage})


async def solve_captcha_visible(url: str, council_code: str, wait_seconds: int = 60) -> Optional[dict]:
    """Open a visible browser for the user to solve CAPTCHA, then capture the session.

    If running in a non-interactive environment (Docker, CI), this will
    attempt to auto-solve by waiting for the invisible captcha to pass.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="en-GB",
        )
        page = await ctx.new_page()

        # Navigate to the URL
        await page.goto(url)
        logger.info(f"Visible browser opened at {url}")
        logger.info(f"Solve the CAPTCHA if prompted. Waiting up to {wait_seconds}s...")

        # Wait for either:
        # 1. Page navigation (captcha solved and form submitted)
        # 2. Captcha token appearing
        # 3. Timeout
        for i in range(wait_seconds * 2):
            await asyncio.sleep(0.5)

            # Check if captcha was solved (token appeared)
            token = await page.evaluate("""() => {
                try {
                    let resp = document.querySelector('textarea[name="g-recaptcha-response"]');
                    return resp ? resp.value : '';
                } catch(e) { return ''; }
            }""")

            if token:
                logger.info("CAPTCHA token detected, capturing session")
                session = await capture_session(page)
                session["captcha_token"] = token
                await browser.close()
                save_session(council_code, session)
                return session

            # Check if page navigated away (form submitted)
            if "Search/Results" in page.url or "results" in page.url.lower():
                logger.info("Page navigated to results, capturing session")
                session = await capture_session(page)
                await browser.close()
                save_session(council_code, session)
                return session

        # Timeout — capture whatever we have
        logger.warning("Timeout waiting for CAPTCHA solve, capturing current session")
        session = await capture_session(page)
        await browser.close()
        save_session(council_code, session)
        return session


async def get_session_for_council(council_code: str, url: str) -> Optional[dict]:
    """Get a valid session for a CAPTCHA-protected council.

    Checks cache first, then opens visible browser if needed.
    """
    # Try cached session
    session = load_session(council_code)
    if session:
        logger.info(f"Using cached session for {council_code}")
        return session

    # Need to solve — check if we're in interactive mode
    if os.environ.get("NONINTERACTIVE") or os.environ.get("CI"):
        logger.warning(f"Cannot solve CAPTCHA for {council_code} in non-interactive mode")
        return None

    return await solve_captcha_visible(url, council_code)
