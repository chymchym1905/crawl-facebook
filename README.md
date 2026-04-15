# Facebook Group Crawler

Authenticated Playwright-based crawler for Facebook group posts. Extracts post content, images, author, timestamp, and full comment threads (including nested replies and comment images) via the post modal.

## Requirements

- Python 3.11+
- [Playwright](https://playwright.dev/python/) for Python

```bash
pip install -r requirements.txt
playwright install chromium
```

## Setup

### 1. Credentials

Create a `config.env` file in the project root:

```env
FB_EMAIL=your@email.com
FB_PASSWORD=yourpassword
```

### 2. Cookies (optional but recommended)

Facebook will prevent you from logging in after a certain amount of attempts, so it's recommended to use cookies. Export your Facebook session cookies from the browser using a cookie-export extension (e.g. [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)) and save the JSON file as `www.facebook.com_cookies.json` in the project root.

The crawler will try cookie login first, and fall back to form login if no cookies file is found.

### 3. Target Group

The default target group URL is set in [`src/config.py`](src/config.py):

```python
TARGET_URL = "https://www.facebook.com/groups/950437708832783"
```

Change this to your target group URL.

## Usage

### Crawl posts from the group feed

```bash
# Crawl the default number of posts (TARGET_POSTS in config.py, default: 3)
python main.py

# Crawl up to 10 posts
python main.py --max-posts 10
```

### Extract a single specific post

```bash
python main.py --post-url "https://www.facebook.com/groups/950437708832783/posts/2145683625974846/"
```

When using `--post-url`, the script navigates directly to the post URL. Facebook automatically opens the post modal, so the crawler immediately waits for the modal, switches to "All comments", and extracts the post — no feed scrolling needed.

### Headless mode

By default, the browser runs **headed** (visible window) so you can observe it and complete 2FA if needed. To run without a browser window:

```bash
python main.py --headless
python main.py --headless --max-posts 10
python main.py --headless --post-url "https://..."
```

> **Note:** Headless mode may be less reliable if Facebook detects automation. Use it only after you have a valid authenticated session via cookies.

## CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--max-posts N` | `3` | Number of posts to crawl from the feed |
| `--post-url URL` | — | Extract a single specific post by URL |
| `--headless` | off | Run browser in headless (windowless) mode |

## Output

Results are saved to `output/posts.json`:

```json
{
  "group_url": "https://www.facebook.com/groups/950437708832783",
  "crawled_at": "2026-04-15T02:37:14Z",
  "timezone": "SE Asia Standard Time (UTC+07:00)",
  "login_status": "authenticated",
  "group_meta": {
    "name": "...",
    "description": "..."
  },
  "posts_count": 3,
  "posts": [
    {
      "post_url": "https://...",
      "author": "...",
      "timestamp": "Wednesday 15 April 2026 at 08:55",
      "text": "...",
      "images": ["https://scontent.fbcdn.net/..."],
      "comments": [
        {
          "author": "...",
          "text": "...",
          "images": [],
          "timestamp": "",
          "is_reply": false
        }
      ]
    }
  ]
}
```

A screenshot of the final page state is saved to `output/screenshot.png`.

## Configuration

All tunable parameters are in [`src/config.py`](src/config.py):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TARGET_URL` | group URL | Facebook group URL to crawl |
| `TARGET_POSTS` | `3` | Default number of posts to extract |
| `MAX_SCROLLS` | `200` | Safety cap on feed scroll iterations |
| `SCROLL_DELAY_MS` | `2000` | Delay between feed scrolls (ms) |
| `INITIAL_WAIT_MS` | `4000` | Wait after page navigation (ms) |
| `MODAL_SCROLL_COUNT` | `30` | Number of scrolls inside post modal |
| `MODAL_SCROLL_DELAY_MS` | `1000` | Delay between modal scrolls (ms) |
| `MAX_COMMENTS` | `200` | Max comments to extract per post |
| `MAX_EXPAND_ITERATIONS` | `50` | Max iterations for expanding reply threads |
| `EXTRACT_COMMENT_TIMESTAMPS` | `False` | Hover-extract absolute timestamps for each comment (slow) |
| `RANDOM_DELAY_MIN/MAX` | `0.0` / `1.5` | Random delay range between interactions (seconds) |

## Project Structure

```
crawl-facebook/
├── main.py                  # Entry point with argparse CLI
├── src/
│   ├── __init__.py
│   ├── config.py            # All constants, paths, CSS selectors
│   ├── auth.py              # Credential loading, cookie login, form login
│   ├── browser.py           # Browser profile, random delay, context launch
│   ├── extractor.py         # Post/comment/image/timestamp extraction
│   └── crawler.py           # Feed crawl loop, single-post extraction
├── requirements.txt
├── config.env               # FB credentials (git-ignored)
├── www.facebook.com_cookies.json  # Exported cookies (optional)
└── output/
    ├── posts.json
    └── screenshot.png
```

## How It Works

### Feed Crawl Mode

1. Launch Chromium (headed by default) with a persistent browser profile
2. Log in via cookies → form login fallback
3. Navigate to the target group URL
4. For each post in the feed:
   - Scroll the post into view
   - Click the "Leave a comment" button to open the post modal
   - Switch the comment filter to "All comments"
   - Scroll the modal to load all comments
   - Expand all "View more comments" and "View N replies" threads via a `while` loop — after each click, polls the DOM until new articles appear (content-based wait, avoids loading-spinner race conditions)
   - Extract: author, timestamp (via hover tooltip), text, images, comments (with images)
   - Close the modal (Escape)
5. Save results to `output/posts.json`

### Single Post Mode (`--post-url`)

1. Log in (same as above)
2. Navigate directly to the post URL — Facebook opens the modal automatically
3. Switch to "All comments" and extract
4. Save results

## Notes

- The browser runs in **headed mode by default** so you can observe it and complete 2FA if required
- Use `--headless` for unattended/CI runs after establishing an authenticated session via cookies
- A persistent browser profile is stored in `.browser_profile/` — cookies and session data are preserved across runs, reducing repeated logins
- Notification permission prompts are blocked at the browser level (`--disable-notifications`, `--deny-permission-prompts`)
- Post timestamps are extracted by hovering over the timestamp element to read the absolute datetime tooltip
- Comment timestamps are disabled by default (`EXTRACT_COMMENT_TIMESTAMPS = False`) as they significantly slow down extraction
