"""
Browser helpers — random delay, profile setup, and Playwright context launch.

Depends on: src.config
"""

import os
import random

from playwright.async_api import Page, BrowserContext

from src.config import (
    BROWSER_PROFILE,
    RANDOM_DELAY_MIN,
    RANDOM_DELAY_MAX,
    USER_AGENTS,
)


# ─── Random Delay ─────────────────────────────────────────────────────────────

async def random_delay(page: Page) -> None:
    """Wait a random interval between RANDOM_DELAY_MIN and RANDOM_DELAY_MAX seconds."""
    delay_ms = int(random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX) * 1000)
    if delay_ms > 0:
        await page.wait_for_timeout(delay_ms)


# ─── Browser Profile ──────────────────────────────────────────────────────────

def ensure_browser_profile() -> None:
    """Create the persistent browser profile directory if it does not exist."""
    os.makedirs(BROWSER_PROFILE, exist_ok=True)


# ─── Context Launch ───────────────────────────────────────────────────────────

async def launch_browser_context(pw, *, headless: bool = False) -> tuple[BrowserContext, Page]:
    """
    Launch a Chromium persistent context with anti-detection flags and a
    randomly selected user-agent.

    Args:
        pw:       The Playwright instance obtained from ``async_playwright()``.
        headless: Run the browser without a visible window (default: False).

    Returns:
        ``(context, page)`` tuple ready for use.
    """
    user_agent = random.choice(USER_AGENTS)
    print(f"[INFO] User-Agent: {user_agent[:60]}...")
    print(f"[INFO] Headless: {headless}")

    context: BrowserContext = await pw.chromium.launch_persistent_context(
        BROWSER_PROFILE,
        headless=headless,
        viewport={"width": 1280, "height": 900},
        user_agent=user_agent,
        permissions=[],
        args=[
            "--disable-blink-features=AutomationControlled",
            "--deny-permission-prompts",
            "--disable-notifications",
        ],
    )

    page: Page = context.pages[0] if context.pages else await context.new_page()
    return context, page
