"""Resolve Wayland app_ids to display names, icons and freedesktop categories.

Lookup order for an app_id (first hit wins):
  1. desktop file id == app_id                 (org.gnome.Nautilus)
  2. StartupWMClass == app_id                  (code_code)
  3. both of the above, case-insensitively     (Spotify -> StartupWMClass=spotify)
  4. snap naming: "<app>_<app>" / "<snap>_<app>" (firefox -> firefox_firefox)
  5. reverse-DNS tail: org.foo.Bar -> bar
  6. app_id prefix of an id / WMClass           (whatsapp-nativefier-d40211 -> whatsapp)
  7. executable seen for the window == Exec     (from /proc/<pid>/exe)
Anything still unresolved gets a prettified name derived from the app_id.
"""

import locale
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

EXTRA_DATA_DIRS = [
    "~/.local/share/flatpak/exports/share",
    "/var/lib/flatpak/exports/share",
    "/var/lib/snapd/desktop",
    "/usr/local/share",
    "/usr/share",
]

# Shell surfaces whose desktop entries are missing or unhelpful.
BUILTIN_NAMES = {
    "org.quickshell": "DankMaterialShell",
    "com.danklinux.dms": "DankMaterialShell",
}

# Executables too generic to identify an app by basename.
GENERIC_EXES = re.compile(r"^(python[\d.]*|electron\d*|java|node|sh|bash|env|flatpak|snap|wine.*|bwrap|gjs|qs|quickshell)$")


@dataclass
class DesktopEntry:
    id: str
    path: str
    name: str
    icon: str = ""
    wm_class: str = ""
    exec_bin: str = ""
    categories: list[str] = field(default_factory=list)
    hidden: bool = False


@dataclass
class AppInfo:
    app_id: str
    name: str
    icon: str
    desktop_id: str | None
    categories: list[str]

    def as_dict(self) -> dict:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "icon": self.icon,
            "desktop_id": self.desktop_id,
        }


def data_dirs() -> list[Path]:
    home = os.environ.get("XDG_DATA_HOME") or "~/.local/share"
    dirs = [home] + (os.environ.get("XDG_DATA_DIRS") or "").split(":") + EXTRA_DATA_DIRS
    seen, result = set(), []
    for d in dirs:
        if not d:
            continue
        p = Path(os.path.expanduser(d)).resolve()
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _locale_keys() -> list[str]:
    lang = os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    if not lang:
        try:
            lang = locale.getlocale()[0] or ""
        except ValueError:
            lang = ""
    lang = lang.split(".")[0].split("@")[0]
    keys = []
    if lang and lang not in ("C", "POSIX"):
        keys.append(f"Name[{lang}]")
        if "_" in lang:
            keys.append(f"Name[{lang.split('_')[0]}]")
    keys.append("Name")
    return keys


def _exec_binary(exec_line: str) -> str:
    try:
        parts = shlex.split(exec_line)
    except ValueError:
        parts = exec_line.split()
    parts = [p for p in parts if not p.startswith("%")]
    # Skip launchers that wrap the real program.
    while parts and (os.path.basename(parts[0]) == "env" or "=" in parts[0]):
        parts = parts[1:]
    if parts and os.path.basename(parts[0]) == "flatpak":
        for p in parts[1:]:
            if not p.startswith("-") and p != "run":
                return p
        return ""
    return parts[0] if parts else ""


def parse_desktop_file(path: Path, desktop_id: str, name_keys: list[str]) -> DesktopEntry | None:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    values: dict[str, str] = {}
    in_main = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            if in_main:
                break  # only [Desktop Entry]; actions come after it
            in_main = line == "[Desktop Entry]"
            continue
        if in_main and "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values.setdefault(key.strip(), value.strip())
    if values.get("Type", "Application") != "Application":
        return None
    name = next((values[k] for k in name_keys if values.get(k)), "")
    if not name:
        return None
    return DesktopEntry(
        id=desktop_id,
        path=str(path),
        name=name,
        icon=values.get("Icon", ""),
        wm_class=values.get("StartupWMClass", ""),
        exec_bin=_exec_binary(values.get("Exec", "")),
        categories=[c for c in values.get("Categories", "").split(";") if c],
        hidden=values.get("NoDisplay", "").lower() == "true" or values.get("Hidden", "").lower() == "true",
    )


def scan_desktop_entries(dirs: list[Path] | None = None) -> dict[str, DesktopEntry]:
    """Desktop entries by id. Earlier data dirs shadow later ones (XDG rules)."""
    entries: dict[str, DesktopEntry] = {}
    name_keys = _locale_keys()
    for base in dirs if dirs is not None else data_dirs():
        appdir = base / "applications"
        if not appdir.is_dir():
            continue
        for path in sorted(appdir.rglob("*.desktop")):
            desktop_id = str(path.relative_to(appdir))[: -len(".desktop")].replace("/", "-")
            if desktop_id in entries:
                continue
            entry = parse_desktop_file(path, desktop_id, name_keys)
            if entry:
                entries[desktop_id] = entry
    return entries


def prettify(app_id: str) -> str:
    """Readable fallback name: 'org.foo.my-app' -> 'My App', 'foo_foo' -> 'Foo'."""
    name = app_id
    if "." in name and not name.endswith("."):
        name = name.rsplit(".", 1)[-1]
    parts = name.split("_")
    if len(parts) == 2 and parts[0].lower() == parts[1].lower():
        name = parts[0]
    name = re.sub(r"[-_]+", " ", name).strip()
    if not name:
        return app_id
    if name.islower():
        name = " ".join(w.capitalize() for w in name.split())
    return name


class Resolver:
    def __init__(self, entries: dict[str, DesktopEntry] | None = None, exes: dict[str, str] | None = None):
        self.entries = entries if entries is not None else scan_desktop_entries()
        self.exes = exes or {}
        self._cache: dict[str, AppInfo] = {}
        # Prefer visible entries over NoDisplay helpers (e.g. url handlers).
        ordered = sorted(self.entries.values(), key=lambda e: (e.hidden, e.id))
        self._by_id_ci: dict[str, DesktopEntry] = {}
        self._by_wm: dict[str, DesktopEntry] = {}
        self._by_wm_ci: dict[str, DesktopEntry] = {}
        self._by_exe: dict[str, DesktopEntry] = {}
        for e in ordered:
            self._by_id_ci.setdefault(e.id.lower(), e)
            if e.wm_class:
                self._by_wm.setdefault(e.wm_class, e)
                self._by_wm_ci.setdefault(e.wm_class.lower(), e)
            if e.exec_bin:
                self._by_exe.setdefault(e.exec_bin, e)
                base = os.path.basename(e.exec_bin).lower()
                if not GENERIC_EXES.match(base):
                    self._by_exe.setdefault(base, e)
        self._ordered = ordered

    def find_entry(self, app_id: str) -> DesktopEntry | None:
        if not app_id:
            return None
        lower = app_id.lower()
        hit = self.entries.get(app_id) or self._by_wm.get(app_id)
        if hit:
            return hit
        hit = self._by_id_ci.get(lower) or self._by_wm_ci.get(lower)
        if hit:
            return hit
        # Snap: desktop ids look like "<snap>_<app>.desktop".
        for e in self._ordered:
            if "_" in e.id and e.id.lower().split("_", 1)[1] == lower:
                return e
        # Reverse-DNS tail.
        if "." in app_id:
            tail = lower.rsplit(".", 1)[-1]
            hit = self._by_id_ci.get(tail) or self._by_wm_ci.get(tail)
            if hit:
                return hit
        # Prefix: "whatsapp-nativefier-d40211" -> id/WMClass "whatsapp".
        best = None
        for key, e in list(self._by_id_ci.items()) + list(self._by_wm_ci.items()):
            if len(key) >= 4 and re.match(rf"{re.escape(key)}[-_.]", lower):
                if best is None or len(key) > best[0]:
                    best = (len(key), e)
        if best:
            return best[1]
        # Executable of the window process.
        exe = self.exes.get(app_id)
        if exe:
            base = os.path.basename(exe).lower()
            hit = self._by_exe.get(exe) or (None if GENERIC_EXES.match(base) else self._by_exe.get(base))
            if hit:
                return hit
        return None

    def resolve(self, app_id: str) -> AppInfo:
        cached = self._cache.get(app_id)
        if cached:
            return cached
        e = self.find_entry(app_id)
        if app_id in BUILTIN_NAMES:
            info = AppInfo(app_id, BUILTIN_NAMES[app_id], e.icon if e and e.icon else app_id,
                           e.id if e else None, ["Settings"])
        elif e:
            info = AppInfo(app_id, e.name, e.icon or app_id, e.id, e.categories)
        else:
            info = AppInfo(app_id, prettify(app_id), app_id, None, [])
        self._cache[app_id] = info
        return info
