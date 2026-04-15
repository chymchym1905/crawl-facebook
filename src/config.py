"""
Configuration — all constants, file paths, timing values, selectors, and
user-agent pool used throughout the Facebook Group Crawler.

No internal project imports — this module is the dependency root.
"""

import os

# ─── Paths ────────────────────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TARGET_URL      = "https://www.facebook.com/groups/950437708832783"
BROWSER_PROFILE = os.path.join(_BASE_DIR, ".browser_profile")
OUTPUT_DIR      = os.path.join(_BASE_DIR, "output")
OUTPUT_JSON     = os.path.join(OUTPUT_DIR, "posts.json")
OUTPUT_SCREENSHOT = os.path.join(OUTPUT_DIR, "screenshot.png")
CONFIG_ENV_PATH = os.path.join(_BASE_DIR, "config.env")
COOKIES_FILE    = os.path.join(_BASE_DIR, "www.facebook.com_cookies.json")

# ─── Crawl Limits & Timing ────────────────────────────────────────────────────

TARGET_POSTS            = 3
MAX_SCROLLS             = 200       # Safety cap on total feed scrolls
SCROLL_DELAY_MS         = 2000
INITIAL_WAIT_MS         = 4000
MODAL_SCROLL_COUNT      = 30        # How many times to scroll inside a modal
MODAL_SCROLL_DELAY_MS   = 1000
MAX_COMMENTS            = 200       # Maximum comments to extract per post

# Set True to hover-extract absolute timestamps for each comment (slow)
EXTRACT_COMMENT_TIMESTAMPS = False

# ─── Login ────────────────────────────────────────────────────────────────────

LOGIN_URL                = "https://www.facebook.com/login"
CHECKPOINT_WAIT_TIMEOUT  = 120      # Seconds to wait for user to complete 2FA

# ─── Random Delay ────────────────────────────────────────────────────────────

RANDOM_DELAY_MIN = 0.0   # Minimum random delay between interactions (seconds)
RANDOM_DELAY_MAX = 1.5   # Maximum random delay between interactions (seconds)

# ─── User-Agent Pool ─────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

# ─── CSS Selectors ───────────────────────────────────────────────────────────

# Post modal (specific class to distinguish from Messenger / other dialogs)
POST_MODAL_SELECTOR = (
    "div.x1n2onr6.x1ja2u2z.x1afcbsf.xdt5ytf.x1a2a7pz.x71s49j.x1qjc9v5"
    ".xazwl86.x1hl0hii.x1aq6byr.x2k6n7x.x78zum5.x1plvlek.xryxfnj"
    ".xcatxm7.xrgej4m.xh8yej3"
)

# Post author span inside modal (obfuscated FB classes)
POST_AUTHOR_SPAN_SELECTOR = (
    "span.x193iq5w.xeuugli.x13faqbe.x1vvkbs.x1xmvt09"
    ".x1nxh6w3.x1sibtaa.x1s688f.xi81zsa"
)

# Comment filter dropdown button inside modal (obfuscated FB classes)
COMMENT_FILTER_DROPDOWN_SELECTOR = (
    'div[aria-haspopup="menu"][role="button"]'
    '[class="x1i10hfl xjbqb8w x1ejq31n x18oe1m7 x1sy0etr xstzfhl x972fbf '
    'x10w94by x1qhh985 x14e42zd x9f619 x1ypdohk xt0psk2 x3ct3a4 xdj266r '
    'x14z9mp xat24cr x1lziwak xexx8yu xyri2b x18d9i69 x1c1uobl x16tdsg8 '
    'x1hl2dhg xggy1nq x1fmog5m xu25z0z x140muxe xo1y3bh x1n2onr6 x87ps6o '
    'x1lku1pv x1a2a7pz"]'
)

# Timestamp link element to hover over (obfuscated FB classes)
TIMESTAMP_HOVER_SELECTOR = (
    "a.x1i10hfl.xjbqb8w.x1ejq31n.x18oe1m7.x1sy0etr.xstzfhl.x972fbf"
    ".x10w94by.x1qhh985.x14e42zd.x9f619.x1ypdohk.xt0psk2.x3ct3a4"
    ".xdj266r.x14z9mp.xat24cr.x1lziwak.xexx8yu.xyri2b.x18d9i69"
    ".x1c1uobl.x16tdsg8.x1hl2dhg.xggy1nq.x1a2a7pz.xkrqix3.x1sur9pj"
    ".xi81zsa.x1s688f"
)

# Tooltip span that appears on hover (obfuscated FB classes)
TOOLTIP_SPAN_SELECTOR = (
    "span.x193iq5w.xeuugli.x13faqbe.x1vvkbs.x1xmvt09"
    ".x1nxh6w3.x1sibtaa.xo118bm.xzsf02u"
)

# Loading icon that appears after clicking "View replies" / expand buttons
LOADING_ICON_SELECTOR = 'div[aria-label="Loading"] [data-visualcompletion="loading-state"]'

# Scroll thumb inside modal — used to locate the scrollable content area
MODAL_SCROLL_THUMB_SELECTOR = (
    "div.x1hwfnsy.xjwep3j.x1t39747.x1wcsgtt.x1pczhz8.x5yr21d.xh8yej3"
)

# Maximum iterations for the expand-all-comments while loop (safety cap)
MAX_EXPAND_ITERATIONS = 50
