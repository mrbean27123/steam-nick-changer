"""Interactive Steam login in the system Edge; the only place that uses Playwright."""

import logging
from pathlib import Path

from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)

LOGIN_URL = "https://steamcommunity.com/login/home/?goto=%2Fmy"
LOGIN_TIMEOUT_MS = 10 * 60 * 1000
COOKIE_WAIT_STEPS = 20


def login(auth_state: Path) -> None:
    """Let the user log in to Steam and save the session cookies to auth_state.

    The login counts as done when the page leaves /login and the steamLoginSecure cookie of
    steamcommunity.com exists. Needs Microsoft Edge, no browser is downloaded.

    Raises:
        playwright.sync_api.Error: if Edge cannot be started.
        playwright.sync_api.TimeoutError: if the user does not log in in time.
        RuntimeError: if the page left /login without a session cookie.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL)
        log.info("Waiting for the Steam login in the browser window.")
        page.wait_for_url(lambda url: "/login" not in url, timeout=LOGIN_TIMEOUT_MS)

        # The cookie is set by the login finalisation, which can lag behind the redirect.
        for _ in range(COOKIE_WAIT_STEPS):
            cookies = context.cookies("https://steamcommunity.com")
            if any(c["name"] == "steamLoginSecure" for c in cookies):
                break
            page.wait_for_timeout(500)
        else:
            raise RuntimeError("Steam did not set the steamLoginSecure cookie after login.")

        context.storage_state(path=auth_state)
        browser.close()
    log.info("Login saved.")
