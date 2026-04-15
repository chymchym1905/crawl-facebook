# Facebook Public Group Crawler — Plan

## Target
- URL: `https://www.facebook.com/groups/950437708832783`
- Mode: Login
- Tool: Python + Playwright (Chromium)

## Architecture Flow

- load target url, launch playwright chromium headed mode
- Login with credentials
- Navigate to group post
- Facebook will pop up request to show notifications, close it
- Scroll to each post click on the comment button to show the post modal pop up, focus the modal, and start extract all information inside it
- Extract post content, post images, author, comments, nested comments inside a post
- Extract post timestamp by hovering over the timestamp element to get absolute time from tooltip
- Comment timestamp extraction is optional (controlled by `EXTRACT_COMMENT_TIMESTAMPS`, default `False`)
- Close the modal and continue
- Put a hard limit for number of posts to be crawl
- Save results with current timezone info in the JSON root

## Project File Structure

```
crawl-facebook/
├── main.py                  # Entry point — wires auth, browser, crawl, save
├── src/
│   ├── __init__.py          # Package marker
│   ├── config.py            # All constants, paths, selectors, USER_AGENTS
│   ├── auth.py              # Credential loading, cookie login, form login
│   ├── browser.py           # Browser profile, random delay, context launch
│   ├── extractor.py         # Meta/post/comment/timestamp extraction
│   └── crawler.py           # Notification popup, comment button, crawl loop
├── requirements.txt         # playwright dependency
├── config.env               # FB_EMAIL / FB_PASSWORD (git-ignored)
├── www.facebook.com_cookies.json  # Exported cookies (optional)
├── output/
│   ├── posts.json           # Extracted post data
│   └── screenshot.png       # Final page screenshot
└── plans/
    └── facebook-group-crawler-plan.md
```

## Module Dependency Graph

```
main.py
  ├── src/config.py     (paths, limits)
  ├── src/browser.py    (launch context)  ← src/config.py
  ├── src/auth.py       (login)           ← src/config.py, src/browser.py
  └── src/crawler.py    (crawl loop)      ← src/config.py, src/browser.py, src/extractor.py
        └── src/extractor.py              ← src/config.py, src/browser.py
```

No circular imports — `config.py` is the dependency root with zero internal imports.

## Data Model (posts.json)

```json
{
  "group_url": "https://www.facebook.com/groups/950437708832783",
  "crawled_at": "2026-04-14T07:42:00Z",
  "timezone": "SE Asia Standard Time (UTC+07:00)",
  "login_status": "authenticated",
  "group_meta": {
    "name": "...",
    "description": "..."
  },
  "posts_count": 4,
  "posts": [
    {
      "post_url": "https://www.facebook.com/groups/.../posts/...",
      "author": "...",
      "timestamp": "Tuesday 14 April 2026 at 17:10",
      "text": "...",
      "images": ["https://..."],
      "comments": [ {
        "author": "...",
        "text": "...",
        "timestamp": "",
        "is_reply": false
      }]
    }
  ]
}
```

> **Note:** Post timestamps are extracted via hover-to-tooltip (absolute format).
> Comment timestamps are optional — controlled by `EXTRACT_COMMENT_TIMESTAMPS` (default `False`).
> When disabled, comment `timestamp` is an empty string.

## Implementation Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point — credential loading, browser launch, login, crawl, save |
| `src/config.py` | All constants, paths, CSS selectors, user-agents, timing values |
| `src/auth.py` | `load_credentials()`, `load_cookies_from_file()`, `try_cookie_login()`, `login_to_facebook()` |
| `src/browser.py` | `random_delay()`, `ensure_browser_profile()`, `launch_browser_context()` |
| `src/extractor.py` | `extract_meta()`, `extract_timestamp_by_hover()`, `extract_comments_from_modal()`, `extract_post_from_modal()` |
| `src/crawler.py` | `close_notification_popup()`, `find_comment_button()`, `switch_to_all_comments()`, `run_crawl()` |
| `requirements.txt` | `playwright` dependency |
| `output/posts.json` | Extracted data output |
| `output/screenshot.png` | Visual audit of page state |

## Key Implementation Decisions

| Decision | Choice | Reason |
|---|---|---|
| Browser engine | Chromium via Playwright | Most realistic rendering |
| Headed/headless | headless=False for testing | Easier to inspect rendering |
| Login wall detection | Check for login-form element or /login redirect | Skip gracefully |
| Scroll strategy | Max 3 scrolls, 2s delay each | Polite rate limiting |
| User-agent | Randomized from pool per run | Anti-fingerprinting |
| Output | JSON + screenshot | Auditable results |
| Error handling | Try/except per post element | Partial results still saved |
| Comment expansion | Unified while loop with loading-icon wait | Guarantees all threads expanded |

## Comment/Reply Expansion Strategy

The `extract_comments_from_modal()` function uses a **unified while loop** to expand all comments and nested reply threads:

1. **Count** current `div[role="article"]` elements in the modal (baseline).
2. **Click** any "View more comments" / "View previous comments" buttons.
3. **Click** all "View N replies" buttons (unexpanded reply threads).
4. After each click, **wait for the loading spinner** (`LOADING_ICON_SELECTOR`) to disappear.
5. **Re-count** articles. If count didn't grow and nothing was clicked → all expanded → break.
6. Safety cap: `MAX_EXPAND_ITERATIONS` (default 50) prevents infinite loops.

## What This Script Will NOT Do
- Will NOT bypass CAPTCHA
- Will NOT paginate beyond natively visible content
- Will NOT rotate proxies or IPs

## How to Run

```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```
