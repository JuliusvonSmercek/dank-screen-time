"""User-editable app -> category mapping (~/.config/screentime/categories.toml).

    [apps]
    "code_code" = "Development"
    "firefox_firefox" = "Browsing"

Keys may be a Wayland app_id or a desktop file id (so one line covers apps
whose app_id carries a random suffix). Apps without a mapping are shown as
their own entry in the category breakdown, never as "unknown".
"""

import datetime
import tomllib
from pathlib import Path

from . import paths
from .apps import Resolver

# Checked in order; the first freedesktop category that matches wins.
FREEDESKTOP_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Games", ("Game", "ActionGame", "AdventureGame", "ArcadeGame", "BoardGame", "CardGame",
               "LogicGame", "RolePlaying", "Simulation", "SportsGame", "StrategyGame")),
    ("Browsing", ("WebBrowser",)),
    ("Communication", ("InstantMessaging", "Chat", "Email", "IRCClient", "Telephony",
                       "VideoConference", "ContactManagement", "News")),
    ("Development", ("Development", "IDE", "Building", "Debugger", "RevisionControl",
                     "GUIDesigner", "Profiling", "Translation", "TerminalEmulator", "WebDevelopment")),
    ("Media", ("AudioVideo", "Audio", "Video", "Music", "Player", "Recorder", "TV",
               "Midi", "Mixer", "Sequencer", "Tuner", "DiscBurning")),
    ("Productivity", ("Office", "WordProcessor", "Spreadsheet", "Presentation", "Calendar",
                      "ProjectManagement", "Finance", "Dictionary", "Viewer", "TextEditor",
                      "Science", "Education", "Math", "Engineering")),
    ("Utilities", ("Scanning",)),
    ("Creativity", ("Graphics", "2DGraphics", "3DGraphics", "VectorGraphics", "RasterGraphics",
                    "Photography", "Publishing", "AudioVideoEditing", "Art")),
    ("Utilities", ("Settings", "System", "Utility", "Scanning", "FileManager", "Security", "Monitor",
                   "Accessibility", "PackageManager", "HardwareSettings", "Network")),
]


def derive(freedesktop_categories: list[str]) -> str | None:
    cats = set(freedesktop_categories)
    for name, members in FREEDESKTOP_RULES:
        if cats.intersection(members):
            return name
    return None


def load(path: Path | None = None) -> dict[str, str]:
    path = path or paths.categories_file()
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        return {}
    table = raw.get("apps", {})
    return {str(k): str(v) for k, v in table.items() if isinstance(v, str) and v.strip()}


class Categorizer:
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping
        self.ci = {k.lower(): v for k, v in mapping.items()}

    def category(self, app_id: str, desktop_id: str | None) -> str | None:
        for key in (app_id, desktop_id):
            if key and key in self.mapping:
                return self.mapping[key]
        for key in (app_id, desktop_id):
            if key and key.lower() in self.ci:
                return self.ci[key.lower()]
        return None


def _q(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


HEADER = """\
# Screen Time categories: app -> category.
#
# Keys are Wayland app_ids (see `screentime apps`) or desktop file ids.
# Values are free text; use any category names you like. Apps that are not
# listed here are shown under their own name.
#
# Regenerate missing entries for newly installed apps with:
#   screentime categories generate
# (existing lines are kept untouched).

[apps]
"""


def generate(resolver: Resolver, existing_text: str | None, extra_app_ids: list[str] = ()) -> tuple[str, int]:
    """Return (new file text, number of added entries).

    Existing content is preserved verbatim; entries for installed apps (and
    any app_ids already seen by the tracker) that are missing get appended.
    """
    existing = {}
    if existing_text:
        try:
            existing = tomllib.loads(existing_text).get("apps", {})
        except tomllib.TOMLDecodeError:
            raise ValueError("existing categories file is not valid TOML; fix it first")
    known = {k.lower() for k in existing}

    lines = []
    for entry in sorted(resolver.entries.values(), key=lambda e: e.name.lower()):
        if entry.hidden:
            continue
        cat = derive(entry.categories)
        if cat is None or entry.id.lower() in known:
            continue
        known.add(entry.id.lower())
        lines.append(f"{_q(entry.id)} = {_q(cat)}  # {entry.name}")
    for app_id in extra_app_ids:
        info = resolver.resolve(app_id)
        if app_id.lower() in known or (info.desktop_id and info.desktop_id.lower() in known):
            continue
        cat = derive(info.categories)
        if cat:
            known.add(app_id.lower())
            lines.append(f"{_q(app_id)} = {_q(cat)}  # {info.name}")

    if existing_text:
        text = existing_text if existing_text.endswith("\n") else existing_text + "\n"
        if lines:
            text += f"\n# added {datetime.date.today().isoformat()}\n" + "\n".join(lines) + "\n"
    else:
        text = HEADER + "\n".join(lines) + "\n"
    return text, len(lines)
