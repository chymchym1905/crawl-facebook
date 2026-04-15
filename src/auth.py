"""
Authentication — credential loading, cookie injection, and form-based login
for the Facebook Group Crawler.

Depends on: src.config
"""

import json
import os

from playwright.async_api import Page, BrowserContext

from src.config import (
    CONFIG_ENV_PATH,
    COOKIES_FILE,
    LOGIN_URL,
    CHECKPOINT_WAIT_TIMEOUT,
)
from src.browser import random_delay


# ─── Credential Loading ────────────────────────────────────────────────────────

def load_credentials() -> tuple[str, str]:
    """
    Load FB_EMAIL and FB_PASSWORD from config.env (or environment variables).

    Returns ``("", "")`` if credentials are not found (allows cookie-only login).

    Returns:
        (email, password) tuple — may be empty strings if not configured.
    """
    email    = os.environ.get("FB_EMAIL", "")
    password = os.environ.get("FB_PASSWORD", "")

    if os.path.exists(CONFIG_ENV_PATH):
        print(f"[INFO] Loading credentials from {CONFIG_ENV_PATH}")
        with open(CONFIG_ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key   = key.strip()
                value = value.strip().strip('"').strip("'")
                if key == "FB_EMAIL":
                    email = value
                elif key == "FB_PASSWORD":
                    password = value

    if not email or not password:
        print(
            f"[WARN] Facebook credentials not found (no config.env or missing values).\n"
            f"       Cookie login will be attempted. If it fails, form login won't be possible.\n"
            f"       To enable form login, create {CONFIG_ENV_PATH} with:\n"
            f"         FB_EMAIL=your@email.com\n"
            f"         FB_PASSWORD=yourpassword"
        )
        return "", ""

    print(f"[INFO] Credentials loaded for: {email}")
    return email, password


# ─── Cookie Loading ────────────────────────────────────────────────────────────

def load_cookies_from_file() -> list[dict]:
    """
    Load cookies from the exported JSON file and convert to Playwright format.

    Returns:
        List of cookie dicts ready for ``context.add_cookies()``, or ``[]``
        if the cookies file does not exist.
    """
    if not os.path.exists(COOKIES_FILE):
        return []

    print(f"[COOKIES] Loading cookies from {COOKIES_FILE}")
    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        raw_cookies = json.load(f)

    pw_cookies: list[dict] = []
    for c in raw_cookies:
        cookie: dict = {
            "name":   c["name"],
            "value":  c["value"],
            "domain": c.get("domain", ".facebook.com"),
            "path":   c.get("path", "/"),
        }

        # Playwright uses 'expires' (Unix timestamp), not 'expirationDate'
        if "expirationDate" in c and c["expirationDate"]:
            cookie["expires"] = c["expirationDate"]

        # sameSite mapping
        same_site = c.get("sameSite", "").lower()
        if same_site in ("strict", "lax", "none"):
            cookie["sameSite"] = same_site.capitalize() if same_site != "none" else "None"
        elif same_site == "no_restriction":
            cookie["sameSite"] = "None"
        else:
            cookie["sameSite"] = "Lax"  # safe default

        cookie["secure"]   = c.get("secure", True)
        cookie["httpOnly"] = c.get("httpOnly", False)
        pw_cookies.append(cookie)

    print(f"[COOKIES] Loaded {len(pw_cookies)} cookies")
    return pw_cookies


# ─── Cookie-Based Login ────────────────────────────────────────────────────────

async def try_cookie_login(context: BrowserContext, page: Page) -> bool:
    """
    Attempt to log in by injecting cookies from the exported file.

    Returns:
        ``True`` if the injected cookies result in an authenticated session,
        ``False`` otherwise.
    """
    cookies = load_cookies_from_file()
    if not cookies:
        print("[COOKIES] No cookies file found, skipping cookie login")
        return False

    await context.add_cookies(cookies)
    print("[COOKIES] Cookies injected, navigating to Facebook to verify...")

    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    url = page.url.lower()
    if "/login" not in url and "/checkpoint" not in url:
        print("[COOKIES] Cookie login successful!")
        return True

    print("[COOKIES] Cookie login failed (redirected to login page)")
    return False


# ─── Form-Based Login ─────────────────────────────────────────────────────────

async def login_to_facebook(page: Page, email: str, password: str) -> bool:
    """
    Log into Facebook via the login form. Handles 2FA by waiting for the user
    to complete verification in the browser window.

    Returns:
        ``True`` on successful login, ``False`` otherwise.
    """
    print("[LOGIN] Navigating to Facebook login page...")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    await random_delay(page)

    # Already logged in? (persistent session / cookies)
    if "/login" not in page.url.lower() and "/checkpoint" not in page.url.lower():
        print("[LOGIN] Already logged in!")
        return True

    # Fill email
    print("[LOGIN] Filling in email...")
    await random_delay(page)
    try:
        await page.fill('input[name="email"]', email)
    except Exception:
        await page.fill("#email", email)
    await random_delay(page)

    # Fill password
    print("[LOGIN] Filling in password...")
    await random_delay(page)
    try:
        await page.fill('input[name="pass"]', password)
    except Exception:
        await page.fill("#pass", password)
    await random_delay(page)

    # Click login button — try multiple selectors
    print("[LOGIN] Clicking login button...")
    await random_delay(page)
    login_clicked = False
    login_selectors = [
        ('div[aria-label="Log in"][role="button"]',  "aria-label Log in"),
        ('button[name="login"]',                     "button name=login"),
        ("#loginbutton",                             "#loginbutton"),
        ('button[type="submit"]',                    "button type=submit"),
        ('input[type="submit"]',                     "input type=submit"),
        ('[data-testid="royal_login_button"]',       "data-testid royal_login_button"),
    ]
    for selector, desc in login_selectors:
        try:
            btn = await page.query_selector(selector)
            if btn:
                await btn.click()
                print(f"[LOGIN] Clicked login button via: {desc}")
                login_clicked = True
                break
        except Exception as e:
            print(f"[LOGIN] Selector '{desc}' failed: {e}")

    if not login_clicked:
        print("[LOGIN] All button selectors failed, pressing Enter to submit form...")
        try:
            pass_field = (
                await page.query_selector('input[name="pass"]')
                or await page.query_selector("#pass")
            )
            if pass_field:
                await pass_field.focus()
                await page.keyboard.press("Enter")
                print("[LOGIN] Submitted form via Enter key")
                login_clicked = True
            else:
                await page.keyboard.press("Enter")
                print("[LOGIN] Pressed Enter (no field focused)")
                login_clicked = True
        except Exception as e:
            print(f"[LOGIN] Enter key fallback also failed: {e}")

    await page.wait_for_timeout(3000)

    # Handle 2FA / checkpoint
    url = page.url.lower()
    if "/checkpoint" in url or "two_step_verification" in url:
        print(f"\n{'='*60}")
        print("[LOGIN] 2FA / Security checkpoint detected!")
        print("[LOGIN] Complete verification in the browser window.")
        print(f"[LOGIN] Waiting up to {CHECKPOINT_WAIT_TIMEOUT}s...")
        print(f"{'='*60}\n")

        for i in range(CHECKPOINT_WAIT_TIMEOUT):
            await page.wait_for_timeout(1000)
            current = page.url.lower()
            if "/checkpoint" not in current and "two_step_verification" not in current:
                print("[LOGIN] Checkpoint completed!")
                break
            if i % 10 == 0 and i > 0:
                print(f"[LOGIN] Still waiting... ({i}s)")
        else:
            print("[LOGIN] Timeout. Login may have failed.")
            return False

    await page.wait_for_timeout(2000)

    if "/login" in page.url.lower():
        print("[LOGIN] Still on login page — login failed.")
        return False

    print("[LOGIN] Login successful!")
    return True
