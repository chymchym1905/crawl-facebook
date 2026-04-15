"""
Extraction — all DOM-scraping logic: group metadata, post content, images,
comment threads, and hover-based timestamp resolution.

Depends on: src.config, src.browser
"""

import re

from playwright.async_api import Page, ElementHandle

from src.config import (
    EXTRACT_COMMENT_TIMESTAMPS,
    MAX_COMMENTS,
    MAX_EXPAND_ITERATIONS,
    MODAL_SCROLL_COUNT,
    MODAL_SCROLL_DELAY_MS,
    MODAL_SCROLL_THUMB_SELECTOR,
    POST_AUTHOR_SPAN_SELECTOR,
    POST_MODAL_SELECTOR,
    TIMESTAMP_HOVER_SELECTOR,
    TOOLTIP_SPAN_SELECTOR,
)
from src.browser import random_delay


# ─── Group Metadata ────────────────────────────────────────────────────────────

async def extract_meta(page: Page) -> dict:
    """
    Extract group name and description from ``<meta>`` tags.

    Returns:
        ``{"name": str, "description": str}``
    """
    name = await page.evaluate("""
        () => {
            const og = document.querySelector('meta[property="og:title"]');
            if (og) return og.content;
            return document.title || '';
        }
    """)
    description = await page.evaluate("""
        () => {
            const og = document.querySelector('meta[property="og:description"]');
            if (og) return og.content;
            const desc = document.querySelector('meta[name="description"]');
            if (desc) return desc.content;
            return '';
        }
    """)
    return {"name": name.strip(), "description": description.strip()}


# ─── Tooltip Text ─────────────────────────────────────────────────────────────

async def _find_tooltip_text(page: Page) -> str:
    """
    Try multiple strategies to extract the tooltip text after hovering over
    a timestamp element.

    Strategy order:
    1. Specific CSS class selector (``TOOLTIP_SPAN_SELECTOR``)
    2. ``role="tooltip"`` attribute
    3. ``data-testid`` / ``data-tooltip`` attributes
    4. JavaScript scan for visible date-shaped text in any span
    """
    # Strategy 1: specific CSS class
    tooltip = await page.query_selector(TOOLTIP_SPAN_SELECTOR)
    if tooltip:
        text = (await tooltip.inner_text()).strip()
        if text:
            return text

    # Strategy 2: role="tooltip"
    tooltip = await page.query_selector('[role="tooltip"]')
    if tooltip:
        text = (await tooltip.inner_text()).strip()
        if text:
            return text

    # Strategy 3: data attributes
    tooltip = await page.query_selector('div[data-testid="tooltip"], div[data-tooltip]')
    if tooltip:
        text = (await tooltip.inner_text()).strip()
        if text:
            return text

    # Strategy 4: JS date-pattern scan across all visible spans
    text = await page.evaluate("""
        (tooltipSelector) => {
            const byRole = document.querySelector('[role="tooltip"]');
            if (byRole) {
                const t = byRole.innerText.trim();
                if (t) return t;
            }
            const byClass = document.querySelector(tooltipSelector);
            if (byClass) {
                const t = byClass.innerText.trim();
                if (t) return t;
            }
            const allSpans = document.querySelectorAll('span');
            for (const span of allSpans) {
                const t = span.innerText.trim();
                if (t && /\\d{1,2}\\s+\\w+\\s+\\d{4}/.test(t)) {
                    const rect = span.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        return t;
                    }
                }
            }
            return '';
        }
    """, TOOLTIP_SPAN_SELECTOR)
    if text:
        return text

    return ""


# ─── Hover-Based Timestamp Extraction ─────────────────────────────────────────

async def extract_timestamp_by_hover(container: ElementHandle, page: Page) -> str:
    """
    Extract an absolute timestamp by hovering over the timestamp ``<a>`` link
    inside *container* and reading the resulting tooltip.

    Returns:
        The tooltip text (e.g. ``"Tuesday 14 April 2026 at 17:10"``), or ``""``
        if the element or tooltip cannot be found.
    """
    try:
        ts_link = await container.query_selector(TIMESTAMP_HOVER_SELECTOR)
        if not ts_link:
            print("    [WARN] Timestamp hover element not found")
            return ""

        await ts_link.hover()
        await page.wait_for_timeout(1000)

        text = await _find_tooltip_text(page)
        if text:
            await page.mouse.move(0, 0)
            await page.wait_for_timeout(200)
            print(f"    [DEBUG] Extracted timestamp via hover: '{text}'")
            return text

        # Retry after extra wait
        await page.wait_for_timeout(1000)
        text = await _find_tooltip_text(page)
        if text:
            await page.mouse.move(0, 0)
            await page.wait_for_timeout(200)
            print(f"    [DEBUG] Extracted timestamp via hover (retry): '{text}'")
            return text

        await page.mouse.move(0, 0)
        await page.wait_for_timeout(200)
        print("    [WARN] Tooltip not found after hover")
        return ""

    except Exception as e:
        print(f"    [WARN] Timestamp hover extraction error: {e}")
        try:
            await page.mouse.move(0, 0)
        except Exception:
            pass
        return ""


# ─── Content-Based Wait Helper ────────────────────────────────────────────────

async def _wait_for_new_content(
    modal: ElementHandle,
    page: Page,
    baseline_count: int,
    timeout_ms: int = 10000,
    poll_interval_ms: int = 300,
) -> int:
    """
    After clicking an expand button, poll until the number of article
    elements inside the modal exceeds *baseline_count* — or *timeout_ms*
    elapses, whichever comes first.

    This avoids the race condition with the loading spinner (which can
    appear and disappear faster than Playwright can detect it).

    Args:
        modal:           The modal ``ElementHandle`` that contains articles.
        page:            Playwright ``Page`` (used for ``wait_for_timeout``).
        baseline_count:  Number of articles *before* the click.
        timeout_ms:      Maximum time to wait for new content.
        poll_interval_ms: Interval between polls.

    Returns:
        The new article count observed (may equal *baseline_count* on timeout).
    """
    elapsed = 0
    while elapsed < timeout_ms:
        await page.wait_for_timeout(poll_interval_ms)
        elapsed += poll_interval_ms
        articles = await modal.query_selector_all('div[role="article"][aria-label]')
        new_count = len(articles)
        if new_count > baseline_count:
            print(f"    [WAIT] New content loaded: {baseline_count} → {new_count} articles ({elapsed}ms)")
            return new_count
    print(f"    [WAIT] Timeout after {timeout_ms}ms (count still {baseline_count})")
    return baseline_count


# ─── Comment Extraction ────────────────────────────────────────────────────────

async def extract_comments_from_modal(modal: ElementHandle, page: Page) -> list[dict]:
    """
    Extract all comments and nested replies from the open post modal.

    Steps:
    1. Expand "View more comments" links repeatedly.
    2. Expand nested reply threads.
    3. Expand individual "See more" truncations.
    4. Collect ``div[role="article"]`` elements filtered by aria-label.
    5. Parse author, text, optional timestamp, and reply flag for each.

    Returns:
        List of comment dicts: ``{author, text, timestamp, is_reply}``.
    """
    comments: list[dict] = []

    # ── Expand all comments AND nested reply threads in a unified while loop ─
    # Each iteration:
    #   1. Count current comment/reply articles as a baseline.
    #   2. Click any "View more comments" / "View previous comments" buttons.
    #   3. Click any "View N replies" buttons (unexpanded threads).
    #   4. After each click, poll until article count increases (content loaded).
    #   5. If nothing was clicked and count didn't grow → done → break.
    prev_article_count = 0
    iteration = 0

    while iteration < MAX_EXPAND_ITERATIONS:
        iteration += 1

        # Snapshot: how many comment/reply articles do we see right now?
        current_articles = await modal.query_selector_all('div[role="article"][aria-label]')
        current_count = len(current_articles)

        clicked_anything = False

        # ── "View more comments" / "View previous comments" ───────────────
        try:
            expand_btn = await modal.query_selector(
                'div[role="button"] span:has-text("View more comments"), '
                'div[role="button"] span:has-text("Xem thêm bình luận"), '
                'div[role="button"] span:has-text("View previous comments")'
            )
            if expand_btn:
                await expand_btn.click()
                clicked_anything = True
                current_count = await _wait_for_new_content(modal, page, current_count)
        except Exception:
            pass

        # ── "View N replies" / reply expansion buttons ────────────────────
        try:
            reply_btns = await modal.query_selector_all(
                'div[role="button"] span:has-text("repl"), '
                'div[role="button"] span:has-text("phản hồi")'
            )
            for btn in reply_btns:
                try:
                    await random_delay(page)
                    await btn.click()
                    clicked_anything = True
                    current_count = await _wait_for_new_content(modal, page, current_count)
                except Exception:
                    pass
        except Exception:
            pass

        # Final count after this round
        final_articles = await modal.query_selector_all('div[role="article"][aria-label]')
        final_count = len(final_articles)

        print(
            f"    [EXPAND] iteration={iteration}, "
            f"articles: {prev_article_count} → {final_count}, "
            f"clicked_anything={clicked_anything}"
        )

        # Stop if we didn't click anything AND article count didn't grow
        if not clicked_anything and final_count <= prev_article_count:
            break

        prev_article_count = final_count

    # ── Expand individual "See more" truncations ──────────────────────────────
    try:
        see_more_btns = await modal.query_selector_all(
            'div[role="button"]:has-text("See more"), '
            'div[role="button"]:has-text("Xem thêm")'
        )
        for btn in see_more_btns[:30]:
            try:
                await btn.click()
                await page.wait_for_timeout(200)
            except Exception:
                pass
    except Exception:
        pass

    # ── Collect comment/reply articles ────────────────────────────────────────
    all_articles = await modal.query_selector_all('div[role="article"][aria-label]')
    comment_elements: list[tuple[ElementHandle, str]] = []
    for art in all_articles:
        label = (await art.get_attribute("aria-label")) or ""
        lower = label.lower()
        if (
            "comment by" in lower
            or "reply by" in lower
            or "bình luận" in lower
            or "phản hồi" in lower
            or "trả lời" in lower
            or label.startswith("Comment")
            or label.startswith("Reply")
        ):
            comment_elements.append((art, label))

    print(f"    [INFO] Found {len(comment_elements)} comment/reply articles")

    seen_keys: set[str] = set()
    for cel, aria_label in comment_elements:
        if len(comments) >= MAX_COMMENTS:
            print(f"    [INFO] Reached max comments limit ({MAX_COMMENTS}), stopping")
            break

        try:
            # ── Author: parse from aria-label ─────────────────────────────────
            author = ""
            if aria_label:
                # Reply format: "Reply by NAME to ..."
                m = re.match(
                    r'(?:Comment|Reply|Bình luận|Phản hồi|Trả lời)\s+by\s+(.+?)\s+to\s+',
                    aria_label, re.IGNORECASE,
                )
                if not m:
                    # Dot separator format
                    m = re.match(
                        r'(?:Comment|Reply|Bình luận|Phản hồi|Trả lời)\s+by\s+(.+?)\s+·\s+',
                        aria_label, re.IGNORECASE,
                    )
                if not m:
                    # Trailing relative time expression
                    m = re.match(
                        r'(?:Comment|Reply|Bình luận|Phản hồi|Trả lời)\s+by\s+(.+?)\s+'
                        r'(?:\d+\s+(?:hours?|minutes?|seconds?|days?|weeks?|months?|years?)\s+ago'
                        r'|\d+[hdwmys]'
                        r'|just now'
                        r'|yesterday'
                        r'|hôm qua'
                        r'|\d+\s+(?:giờ|phút|giây|ngày|tuần|tháng|năm))',
                        aria_label, re.IGNORECASE,
                    )
                if m:
                    author = m.group(1).strip()

            # Fallback: first meaningful link text inside the article
            if not author:
                author_links = await cel.query_selector_all('a[role="link"]')
                for al in author_links:
                    t = (await al.inner_text()).strip()
                    if t:
                        author = t
                        break

            # ── Text: longest div[dir="auto"] not inside a nested article ──────
            text: str = await page.evaluate("""
                (el) => {
                    const allDirs = Array.from(el.querySelectorAll('div[dir="auto"]'));
                    const candidates = allDirs.filter(d => {
                        let parent = d.parentElement;
                        while (parent && parent !== el) {
                            if (parent.getAttribute('role') === 'article') return false;
                            parent = parent.parentElement;
                        }
                        return true;
                    });
                    if (candidates.length === 0) return '';
                    let best = '';
                    for (const c of candidates) {
                        const t = c.innerText.trim();
                        if (t.length > best.length) best = t;
                    }
                    return best;
                }
            """, cel)

            # ── Images: fbcdn images scoped to this article, not nested ones ──
            comment_images: list[str] = await page.evaluate("""
                (el) => {
                    const imgs = Array.from(el.querySelectorAll('img[src*="fbcdn.net"]'));
                    const results = [];
                    for (const img of imgs) {
                        const src = img.src;
                        if (!src || src.includes('emoji')) continue;
                        // Skip images inside nested articles (reply avatars)
                        const closestArticle = img.closest('div[role="article"]');
                        if (closestArticle && closestArticle !== el) continue;
                        const w = parseInt(img.getAttribute('width') || '0') || img.naturalWidth || 0;
                        const h = parseInt(img.getAttribute('height') || '0') || img.naturalHeight || 0;
                        if (w > 0 && w < 60) continue;
                        if (h > 0 && h < 60) continue;
                        const ariaLabel = img.getAttribute('aria-label') || '';
                        if (ariaLabel.includes('profile picture')) continue;
                        const alt = img.getAttribute('alt') || '';
                        if (alt.includes('profile picture') || alt.includes('ảnh đại diện')) continue;
                        if (!results.includes(src)) results.push(src);
                    }
                    return results;
                }
            """, cel)

            # ── Timestamp (optional) ──────────────────────────────────────────
            timestamp = ""
            if EXTRACT_COMMENT_TIMESTAMPS:
                timestamp = await extract_timestamp_by_hover(cel, page)

            # ── Skip / dedup logic ────────────────────────────────────────────
            # Allow image-only comments; skip only if BOTH text and images empty
            if not text and not comment_images:
                print(f"    [SKIP] No text and no images (author='{author}', aria='{aria_label[:60]}')")
                continue
            if len(text) > 3000:
                print(f"    [SKIP] Text too long ({len(text)} chars) for article (author='{author}')")
                continue

            # Dedup: use text if available, otherwise use aria_label
            dedup_key = text if text else aria_label
            if dedup_key in seen_keys:
                print(f"    [SKIP] Duplicate (author='{author}', key='{dedup_key[:50]}')")
                continue
            seen_keys.add(dedup_key)

            is_reply = (
                "reply" in aria_label.lower()
                or "phản hồi" in aria_label.lower()
                or "trả lời" in aria_label.lower()
            )
            comments.append({
                "author":    author,
                "text":      text,
                "images":    comment_images,
                "timestamp": timestamp,
                "is_reply":  is_reply,
            })

        except Exception as e:
            print(f"    [WARN] Comment extraction error: {e}")
            continue

    return comments


# ─── Post Extraction from Modal ────────────────────────────────────────────────

async def extract_post_from_modal(page: Page) -> dict | None:
    """
    Extract all data for the currently-open post modal.

    Waits for the modal selector, scrolls to load all comments, then extracts:
    post URL, author, timestamp, text, images, and comments.

    Returns:
        Post data dict, or ``None`` if the modal cannot be found or the post
        has neither text nor images.
    """
    # ── Wait for modal ─────────────────────────────────────────────────────────
    modal = None
    try:
        await page.wait_for_selector(POST_MODAL_SELECTOR, state="attached", timeout=10000)
        modal = await page.query_selector(POST_MODAL_SELECTOR)
    except Exception:
        print("  [WARN] Post modal not found after 10s wait")
        return None

    if not modal:
        print("  [WARN] Modal query returned None")
        return None

    # ── Scroll modal to load all comments ─────────────────────────────────────
    scroll_thumb = await modal.query_selector(MODAL_SCROLL_THUMB_SELECTOR)
    mouse_x, mouse_y = 640, 450  # fallback: viewport centre

    if scroll_thumb:
        print("  [INFO] Found scroll thumb inside modal")
        thumb_box = await scroll_thumb.bounding_box()
        if thumb_box:
            mouse_x = int(thumb_box["x"] - 100)
            mouse_y = int(thumb_box["y"] + thumb_box["height"] / 2)
            print(f"  [INFO] Scroll position: ({mouse_x}, {mouse_y})")
    else:
        modal_box = await modal.bounding_box()
        if modal_box:
            mouse_x = int(modal_box["x"] + modal_box["width"] / 2)
            mouse_y = int(modal_box["y"] + modal_box["height"] / 2)
            print(f"  [INFO] Using modal centre for scroll: ({mouse_x}, {mouse_y})")
        else:
            print("  [WARN] Could not determine scroll position, using viewport centre")

    await page.mouse.move(mouse_x, mouse_y)
    await page.wait_for_timeout(300)

    for i in range(MODAL_SCROLL_COUNT):
        try:
            await page.mouse.wheel(0, 1500)
            await page.wait_for_timeout(MODAL_SCROLL_DELAY_MS)
        except Exception as e:
            print(f"  [WARN] Scroll error at iteration {i}: {e}")
            break

    # ── Post URL ───────────────────────────────────────────────────────────────
    post_url = ""
    url_links = await modal.query_selector_all('a[href*="/posts/"]')
    for link in url_links:
        href = await link.get_attribute("href")
        if href and "/posts/" in href:
            post_url = href if href.startswith("http") else f"https://www.facebook.com{href}"
            break

    # ── Author ─────────────────────────────────────────────────────────────────
    author: str = await page.evaluate("""
        ([modal, authorSelector]) => {
            const authorSpan = modal.querySelector(authorSelector);
            if (authorSpan) {
                const t = authorSpan.innerText.trim();
                if (t) return t;
            }
            const links = Array.from(modal.querySelectorAll('a[role="link"]'));
            for (const link of links) {
                const article = link.closest('div[role="article"]');
                if (article) continue;
                const t = link.innerText.trim();
                if (t && t.length < 100) return t;
            }
            return '';
        }
    """, [modal, POST_AUTHOR_SPAN_SELECTOR])
    print(f"  [DEBUG] Post author: '{author}'")

    # ── Timestamp ──────────────────────────────────────────────────────────────
    timestamp = await extract_timestamp_by_hover(modal, page)
    print(f"  [DEBUG] Post timestamp: '{timestamp}'")

    # ── Post Text ──────────────────────────────────────────────────────────────
    text: str = await page.evaluate("""
        (modal) => {
            const adMsg = modal.querySelector(
                'div[data-ad-comet-preview="message"], div[data-ad-preview="message"]'
            );
            if (adMsg) {
                const t = adMsg.innerText.trim();
                if (t) return t;
            }
            const allDirs = Array.from(modal.querySelectorAll('div[dir="auto"]'));
            const candidates = allDirs.filter(el => !el.closest('div[role="article"]'));
            if (candidates.length === 0) return '';
            let best = '';
            for (const el of candidates) {
                const t = el.innerText.trim();
                if (t.length > best.length) best = t;
            }
            return best;
        }
    """, modal)
    print(f"  [DEBUG] Post text length: {len(text)}")

    # ── Images ─────────────────────────────────────────────────────────────────
    images: list[str] = await page.evaluate("""
        (modal) => {
            const imgs   = Array.from(modal.querySelectorAll('img[src*="fbcdn.net"]'));
            const results = [];
            for (const img of imgs) {
                const src = img.src;
                if (!src || src.includes('emoji')) continue;
                if (img.closest('div[role="article"]')) continue;
                const w = parseInt(img.getAttribute('width')  || '0') || img.naturalWidth  || 0;
                const h = parseInt(img.getAttribute('height') || '0') || img.naturalHeight || 0;
                if (w > 0 && w < 100) continue;
                if (h > 0 && h < 100) continue;
                const ariaLabel = img.getAttribute('aria-label') || '';
                if (ariaLabel && ariaLabel.includes('profile picture')) continue;
                const alt = img.getAttribute('alt') || '';
                if (alt.includes('profile picture') || alt.includes('ảnh đại diện')) continue;
                if (!results.includes(src)) results.push(src);
            }
            return results;
        }
    """, modal)
    print(f"  [DEBUG] Post images: {len(images)}")

    # ── Comments ───────────────────────────────────────────────────────────────
    comment_list = await extract_comments_from_modal(modal, page)

    if not text and not images:
        return None

    return {
        "post_url":  post_url,
        "images":    images,
        "author":    author,
        "timestamp": timestamp,
        "text":      text,
        "comments":  comment_list,
    }
