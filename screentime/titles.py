"""Window title clean-up: privacy redaction at record time, grouping at query time."""

import re

MAX_LEN = 300
PRIVATE_WINDOW = "Private window"

# Titles of private/incognito windows are never stored verbatim.
_PRIVATE_RE = re.compile(r"(Private Browsing|\(Private\)|\(Incognito\)|— Incognito\b)", re.IGNORECASE)

# Leading unread counters / unsaved markers: "(3) WhatsApp", "● main.py", "[2] Inbox", "* notes"
_PREFIX_RE = re.compile(r"^\s*(?:\(\d+\+?\)|\[\d+\+?\]|[●•*])\s*")

_SEPARATORS = (" — ", " – ", " - ", " | ", " · ", " :: ")

# Suffixes worth stripping even when they don't match the app's display name.
_KNOWN_SUFFIXES = (
    "mozilla firefox", "firefox", "chromium", "google chrome", "brave", "vivaldi",
    "mozilla thunderbird", "thunderbird", "visual studio code", "code - oss", "vscodium",
    "cursor", "zed", "obsidian", "libreoffice",
)


def redact(title: str | None) -> str | None:
    """Applied by the daemon before a title is written to disk."""
    if not title:
        return None
    if _PRIVATE_RE.search(title):
        return PRIVATE_WINDOW
    return title[:MAX_LEN]


def _is_app_suffix(segment: str, app_name: str) -> bool:
    seg = segment.strip().lower()
    if not seg:
        return True
    name = app_name.strip().lower()
    if seg in _KNOWN_SUFFIXES or seg == name:
        return True
    if len(name) >= 4 and (name in seg or seg in name):
        return True
    return False


def normalize(title: str | None, app_name: str = "") -> str:
    """Group-friendly title: no unread counters, no trailing "— App Name"."""
    if not title:
        return ""
    if title == PRIVATE_WINDOW:
        return title
    text = _PREFIX_RE.sub("", title.strip())
    # Peel app-name suffixes off the right end ("Page — Mozilla Firefox").
    changed = True
    while changed:
        changed = False
        for sep in _SEPARATORS:
            head, found, tail = text.rpartition(sep)
            if found and head.strip() and _is_app_suffix(tail, app_name):
                text = head.strip()
                changed = True
                break
    text = _PREFIX_RE.sub("", text).strip()
    # A title that is just the app's name says nothing about the window.
    if text.lower() in _KNOWN_SUFFIXES or text.lower() == app_name.strip().lower():
        return ""
    return text
