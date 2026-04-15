"""
Crawler — feed-level orchestration: notification popup, comment button
detection, comment filter switching, and the main scroll-and-extract loop.

Depends on: src.config, src.browser, src.extractor
"""

import re

from playwright.async_api import Page, ElementHandle

from src.config import (
    COMMENT_FILTER_DROPDOWN_SELECTOR,
    INITIAL_WAIT_MS,
    MAX_SCROLLS,
    POST_MODAL_SELECTOR,
    SCROLL_DELAY_MS,
    TARGET_URL,
)
from src.browser import random_delay
from src.extractor import extract_meta, extract_post_from_modal


# ─── Comment Button ────────────────────────────────────────────────────────────

async def find_comment_button(post_el: ElementHandle) -> ElementHandle | None:
    """
    Find the "Leave a comment" button on a feed post element.
    Clicking it opens the post modal / popup that contains comments.
    """
    selectors = [
        'div[aria-label="Leave a comment"][role="button"]',
        'div[aria-label*="Leave a comment"][role="button"]',
        'div[aria-label*="Comment"][role="button"]',
        'div[aria-label*="comment"][role="button"]',
        'div[aria-label*="Bình luận"][role="button"]',
    ]
    for sel in selectors:
        try:
            btn = await post_el.query_selector(sel)
            if btn:
                return btn
        except Exception:
            continue

    # Fallback: text-based search
    try:
        action_btns = await post_el.query_selector_all('div[role="button"]')
        for btn in action_btns:
            text = (await btn.inner_text()).strip().lower()
            if "comment" in text or "bình luận" in text:
                return btn
    except Exception:
        pass

    return None


# ─── Comment Filter Switch ─────────────────────────────────────────────────────

async def switch_to_all_comments(page: Page) -> bool:
    """
    After the comment button opens the post modal, click the "Most relevant"
    dropdown and select "All comments" to load every comment for scraping.

    Returns:
        ``True`` on success (or if no dropdown exists), ``False`` on failure.
    """
    try:
        try:
            await page.wait_for_selector(POST_MODAL_SELECTOR, state="attached", timeout=10000)
            print("  [INFO] Post modal detected, looking for comment filter dropdown...")
        except Exception:
            print("  [WARN] Post modal not found while trying to switch comments filter")
            return False

        modal = page.locator(POST_MODAL_SELECTOR).first

        # Try the exact class selector first
        dropdown = modal.locator(COMMENT_FILTER_DROPDOWN_SELECTOR).first
        if await dropdown.count() == 0:
            dropdown = modal.locator('div[role="button"]').filter(
                has_text=re.compile(r"Most relevant|Newest|Phù hợp nhất|Mới nhất", re.IGNORECASE)
            ).first

        if await dropdown.count() > 0:
            await dropdown.click()
            print("  [INFO] Clicked comment filter dropdown")
            await page.wait_for_timeout(1500)

            # Scan menu items for "All comments"
            menu_items = page.locator('div[role="menuitem"], div[role="option"]')
            count = await menu_items.count()
            for i in range(count):
                item = menu_items.nth(i)
                text = (await item.inner_text()).strip().lower()
                if "potential spam" in text or "tất cả" in text:
                    await item.click()
                    print("  [INFO] Selected 'All comments'")
                    await page.wait_for_timeout(2000)
                    return True

            # Fallback: menu text
            all_btn = page.locator(
                'div[role="menu"] >> text=/All comments|Tất cả bình luận/i'
            ).first
            if await all_btn.count() > 0:
                await all_btn.click()
                print("  [INFO] Selected 'All comments' (menu text fallback)")
                await page.wait_for_timeout(2000)
                return True

            # Fallback: span text
            all_span = page.locator(
                'span:has-text("All comments"), span:has-text("Tất cả bình luận")'
            ).first
            if await all_span.count() > 0:
                await all_span.click()
                print("  [INFO] Selected 'All comments' (span text fallback)")
                await page.wait_for_timeout(2000)
                return True

            # Close menu if "All comments" not found
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
            print("  [WARN] 'All comments' option not found in dropdown menu")
            return False

        else:
            print("  [INFO] No comment filter dropdown found (may already show all)")
            # Click something neutral to unfocus text input
            try:
                heading = modal.locator("h2, h3, h4, span[dir='auto']").first
                if await heading.count() > 0:
                    await heading.click()
                    await page.wait_for_timeout(300)
            except Exception:
                pass
            return True

    except Exception as e:
        print(f"  [WARN] Could not switch to all comments: {e}")
        return False


# ─── Single Post Extraction ───────────────────────────────────────────────────

async def run_single_post(page: Page, post_url: str) -> tuple[dict, list[dict]]:
    """
    Navigate directly to a single post URL and extract it.

    When navigating to a Facebook post URL, the post modal opens
    automatically.  This function:

    1. Navigates to the post URL.
    2. Closes the notification popup if present.
    3. Waits for the post modal to appear.
    4. Switches to "All comments" filter.
    5. Extracts the post from the already-open modal.

    Args:
        page:     A Playwright ``Page`` that is already logged in.
        post_url: The full Facebook post URL.

    Returns:
        ``(group_meta, posts)`` — *posts* contains at most one item.
    """
    print(f"\n[STEP 2] Navigating to post URL: {post_url}")
    await page.goto(post_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(INITIAL_WAIT_MS)

    # Extract page metadata (group name / description from <meta> tags)
    group_meta = await extract_meta(page)
    print(f"[INFO] Page: {group_meta['name']}")

    # The post modal should already be open from navigating to the URL.
    # Wait for it to be present in the DOM.
    print("\n[STEP 4] Waiting for post modal (auto-opened by URL)...")
    try:
        await page.wait_for_selector(POST_MODAL_SELECTOR, state="attached", timeout=15000)
        print("  [INFO] Post modal detected")
    except Exception:
        print("  [WARN] Post modal not detected after 15s — attempting extraction anyway")

    # Switch to "All comments" via the filter dropdown
    print("[STEP 5] Switching to 'All comments' and extracting...")
    await switch_to_all_comments(page)
    await random_delay(page)

    # Extract the post from the already-open modal
    post_data = await extract_post_from_modal(page)
    posts: list[dict] = []
    if post_data:
        if not post_data["post_url"]:
            post_data["post_url"] = post_url
        posts.append(post_data)
        print(
            f"  [OK] author='{post_data['author']}', "
            f"comments={len(post_data['comments'])}, "
            f"images={len(post_data['images'])}"
        )
    else:
        print("  [WARN] Could not extract post from modal")

    return group_meta, posts


# ─── Main Crawl Loop ──────────────────────────────────────────────────────────

async def run_crawl(page: Page, target_posts: int | None = None) -> tuple[dict, list[dict]]:
    """
    Execute the full crawl pipeline on an authenticated page:

    1. Navigate to the target group URL.
    2. Close notification popup.
    3. Extract group metadata.
    4. Iterate feed posts, open each modal, extract data, close modal.
    5. Scroll to load more posts until *target_posts* reached or limits hit.

    Args:
        page:         A Playwright ``Page`` that is already logged in to Facebook.
        target_posts: Maximum number of posts to extract (defaults to config
                      ``TARGET_POSTS`` if ``None``).

    Returns:
        ``(group_meta, posts)`` where *group_meta* is ``{"name", "description"}``
        and *posts* is a list of post dicts.
    """
    from src.config import TARGET_POSTS as _DEFAULT_TARGET
    max_posts = target_posts if target_posts is not None else _DEFAULT_TARGET

    # ── Navigate to group ──────────────────────────────────────────────────────
    print("\n[STEP 2] Navigating to group...")
    await page.goto(TARGET_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(INITIAL_WAIT_MS)

    # ── Extract group metadata ─────────────────────────────────────────────────
    print("\n[STEP 4] Extracting group metadata...")
    group_meta = await extract_meta(page)
    print(f"[INFO] Group: {group_meta['name']}")

    # ── Crawl posts via modal ──────────────────────────────────────────────────
    print(f"\n[STEP 5] Crawling {max_posts} posts via modal extraction...")
    posts: list[dict] = []
    processed_post_ids: set[str] = set()
    scroll_count     = 0
    stale_rounds     = 0
    last_post_count  = 0

    while len(posts) < max_posts and scroll_count < MAX_SCROLLS:
        feed_children = await page.query_selector_all('div[role="feed"] > div')

        for child in feed_children:
            if len(posts) >= max_posts:
                break

            try:
                article = await child.query_selector('div[role="article"]')
                if not article:
                    continue

                # Unique post ID from URL
                post_id = None
                url_links = await child.query_selector_all('a[href*="/posts/"]')
                for link in url_links:
                    href = await link.get_attribute("href")
                    if href:
                        match = re.search(r"/posts/(\d+)", href)
                        if match:
                            post_id = match.group(1)
                            break

                if not post_id or post_id in processed_post_ids:
                    continue

                processed_post_ids.add(post_id)

                print(f"\n[POST {len(posts) + 1}/{max_posts}] Processing post {post_id}...")

                await child.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                await random_delay(page)

                # Find and click comment button
                comment_btn = await find_comment_button(child)
                if not comment_btn:
                    print("  [WARN] No comment button found, skipping")
                    continue

                await random_delay(page)
                await comment_btn.click()
                await page.wait_for_timeout(2000)
                await random_delay(page)

                # Switch to "All comments"
                await switch_to_all_comments(page)
                await random_delay(page)

                # Extract from modal
                post_data = await extract_post_from_modal(page)
                if post_data:
                    if not post_data["post_url"]:
                        for link in url_links:
                            href = await link.get_attribute("href")
                            if href and "/posts/" in href:
                                post_data["post_url"] = (
                                    href if href.startswith("http")
                                    else f"https://www.facebook.com{href}"
                                )
                                break
                    posts.append(post_data)
                    print(
                        f"  [OK] author='{post_data['author']}', "
                        f"comments={len(post_data['comments'])}, "
                        f"images={len(post_data['images'])}"
                    )
                else:
                    print("  [WARN] Could not extract post from modal")

                # Close modal
                await random_delay(page)
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(1000)

                still_open = await page.query_selector(POST_MODAL_SELECTOR)
                if still_open:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                await random_delay(page)

            except Exception as e:
                print(f"  [ERROR] Failed to process post: {e}")
                try:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                except Exception:
                    pass
                continue

        # Stale detection
        if len(posts) == last_post_count:
            stale_rounds += 1
            if stale_rounds >= 5:
                print(f"\n[INFO] No new posts after {stale_rounds} stale rounds. Stopping.")
                break
        else:
            stale_rounds = 0
        last_post_count = len(posts)

        # Scroll for more posts
        if len(posts) < max_posts:
            scroll_count += 1
            print(f"[SCROLL] Scroll {scroll_count}, posts so far: {len(posts)}")
            await page.evaluate("window.scrollBy(0, 1500)")
            await page.wait_for_timeout(SCROLL_DELAY_MS)

    return group_meta, posts
