"""
Facebook Public Group Crawler — Entry Point

Usage:
    python main.py                          # Crawl TARGET_POSTS (default 3) posts from the group feed
    python main.py --max-posts 10           # Crawl up to 10 posts
    python main.py --post-url <URL>         # Extract a single specific post by URL

Flow:
  1. Launch Chromium headed with persistent browser profile
  2. Login with credentials from config.env (cookies → form fallback)
  3a. (feed mode) Navigate to group, scroll feed, extract posts via modal
  3b. (single-post mode) Navigate directly to the post URL, extract it
  4. Save to output/posts.json + screenshot
"""

import argparse
import asyncio
import json
import os
import time as _time
from datetime import datetime, timezone

from playwright.async_api import async_playwright

from src.config import (
    OUTPUT_DIR,
    OUTPUT_JSON,
    OUTPUT_SCREENSHOT,
    TARGET_URL,
    TARGET_POSTS,
)
from src.browser import ensure_browser_profile, launch_browser_context
from src.auth import load_credentials, try_cookie_login, login_to_facebook
from src.crawler import run_crawl, run_single_post


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Facebook Public Group Crawler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--post-url",
        type=str,
        default=None,
        help="Extract a single post by its full Facebook URL (skips feed crawl)",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=None,
        help=f"Maximum number of posts to crawl from the feed (default: {TARGET_POSTS})",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run the browser in headless mode (default: headed/visible)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # Resolve target posts count
    max_posts = args.max_posts if args.max_posts is not None else TARGET_POSTS

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load credentials
    try:
        email, password = load_credentials()
    except ValueError as e:
        print(f"[ERROR] {e}")
        return

    ensure_browser_profile()

    if args.post_url:
        print(f"[INFO] Mode: single post")
        print(f"[INFO] Post URL: {args.post_url}")
    else:
        print(f"[INFO] Mode: feed crawl")
        print(f"[INFO] Target: {TARGET_URL}")
        print(f"[INFO] Max posts: {max_posts}")

    async with async_playwright() as pw:
        context, page = await launch_browser_context(pw, headless=args.headless)

        # ── Step 1: Login (cookies first, then form) ────────────────────────
        print("\n[STEP 1] Logging in...")
        login_ok = await try_cookie_login(context, page)
        if not login_ok:
            print("[INFO] Cookie login failed or no cookies, falling back to form login...")
            login_ok = await login_to_facebook(page, email, password)
        if not login_ok:
            print("[ERROR] Login failed. Aborting.")
            await context.close()
            return

        # ── Steps 2+: Crawl or extract single post ──────────────────────────
        if args.post_url:
            group_meta, posts = await run_single_post(page, args.post_url)
        else:
            group_meta, posts = await run_crawl(page, target_posts=max_posts)

        # ── Save results ────────────────────────────────────────────────────
        print(f"\n[STEP 6] Saving {len(posts)} posts...")

        await page.screenshot(path=OUTPUT_SCREENSHOT, full_page=False)
        print(f"[INFO] Screenshot -> {OUTPUT_SCREENSHOT}")

        # Timezone info
        local_tz   = _time.strftime("%Z")      # e.g. "ICT", "EST"
        utc_offset = _time.strftime("%z")       # e.g. "+0700"

        output_data = {
            "group_url":    TARGET_URL,
            "crawled_at":   datetime.now(timezone.utc).isoformat(),
            "timezone": (
                f"{local_tz} (UTC{utc_offset[:3]}:{utc_offset[3:]})"
                if utc_offset else local_tz
            ),
            "login_status": "authenticated",
            "group_meta":   group_meta,
            "posts_count":  len(posts),
            "posts":        posts,
        }

        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Data -> {OUTPUT_JSON}")

        print(f"\n[DONE] {len(posts)} posts extracted and saved.")
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
