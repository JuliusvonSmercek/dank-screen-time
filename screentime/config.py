"""Daemon configuration (~/.config/screentime/config.toml).

The file is the single source of truth. The DMS plugin writes to it through
`screentime config set`, and the daemon reloads it when its mtime changes.
"""

import os
import re
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from . import paths


@dataclass
class Config:
    # Seconds without input before time stops counting. 0 disables idle detection.
    idle_timeout: int = 300
    # Store window titles alongside app ids (privacy: off by default).
    track_titles: bool = False
    # Window titles older than this are deleted (app time is kept). 0 = keep forever.
    title_retention_days: int = 30
    # Local hour at which a new day starts (0 = midnight).
    day_start_hour: int = 0
    # How often the open interval is flushed to disk (bounds data loss on crash).
    heartbeat_seconds: int = 5

    def validate(self) -> "Config":
        self.idle_timeout = max(0, int(self.idle_timeout))
        self.track_titles = bool(self.track_titles)
        self.title_retention_days = max(0, int(self.title_retention_days))
        self.day_start_hour = min(23, max(0, int(self.day_start_hour)))
        self.heartbeat_seconds = min(60, max(1, int(self.heartbeat_seconds)))
        return self


FIELD_TYPES = {f.name: f.type for f in fields(Config)}


def load(path: Path | None = None) -> Config:
    path = path or paths.config_file()
    cfg = Config()
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except FileNotFoundError:
        return cfg
    except (tomllib.TOMLDecodeError, OSError):
        return cfg
    for key, value in raw.items():
        if key in FIELD_TYPES:
            try:
                setattr(cfg, key, value)
            except (TypeError, ValueError):
                pass
    try:
        return cfg.validate()
    except (TypeError, ValueError):
        return Config()


def parse_value(key: str, text: str):
    kind = FIELD_TYPES.get(key)
    if kind is None:
        raise KeyError(key)
    if kind in (bool, "bool"):
        lowered = text.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ValueError(f"{key} expects true/false, got {text!r}")
    return int(text)


def _toml_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(int(value))


def set_value(key: str, value, path: Path | None = None) -> None:
    """Set one key, keeping comments and the rest of the file intact."""
    path = path or paths.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = path.read_text()
    except FileNotFoundError:
        text = ""
    line = f"{key} = {_toml_literal(value)}"
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
