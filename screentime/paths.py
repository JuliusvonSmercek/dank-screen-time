"""XDG locations used by the daemon and the CLI."""

import os
from pathlib import Path

APP = "screentime"


def _xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var, "")
    return Path(value) if value and os.path.isabs(value) else Path.home() / fallback


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / APP


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / APP


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(base) / APP


def private_umask() -> None:
    """Files we create (database, logs, status) are readable by the user only."""
    os.umask(0o077)


def secure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def config_file() -> Path:
    return config_dir() / "config.toml"


def categories_file() -> Path:
    return config_dir() / "categories.toml"


def db_file() -> Path:
    return data_dir() / "screentime.db"


def status_file() -> Path:
    return runtime_dir() / "status.json"
