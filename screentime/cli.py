"""Command line interface: `screentime <command>`."""

import argparse
import datetime as dt
import json
import sys
import time

from . import __version__, paths
from . import categories as categories_mod
from . import config as config_mod
from .apps import Resolver
from .query import daemon_status, format_duration, summarize
from .store import Store


def _open_store(readonly: bool = True) -> Store | None:
    db = paths.db_file()
    if readonly and not db.exists():
        return None
    return Store(db, readonly=readonly)


def _resolver(store: Store | None) -> Resolver:
    return Resolver(exes=store.app_exes() if store else {})


def cmd_daemon(args) -> int:
    from . import daemon

    return daemon.run(verbose=args.verbose)


def cmd_summary(args) -> int:
    cfg = config_mod.load()
    store = _open_store()
    anchor = dt.date.fromisoformat(args.date) if args.date else None
    resolver = _resolver(store)
    data = summarize(
        store, kind=args.range, anchor=anchor, day_start_hour=cfg.day_start_hour,
        resolver=resolver, categorizer=categories_mod.Categorizer(categories_mod.load()),
    )
    if args.json:
        json.dump(data, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
        return 0
    rng = data["range"]
    span = rng["start"] if rng["start"] == rng["end"] else f"{rng['start']} – {rng['end']}"
    print(f"{rng['kind'].capitalize()} {span}: {format_duration(data['total_seconds'])}"
          f"  (daily avg baseline {format_duration(data['average_seconds'])})")
    if not data["daemon"]["running"]:
        print("warning: tracker daemon is not running")
    width = max((len(a["name"]) for a in data["apps"]), default=0)
    for app in data["apps"][: args.limit]:
        cat = app["category"] or "—"
        print(f"  {app['name']:<{width}}  {format_duration(app['seconds']):>12}  {app['share'] * 100:5.1f}%  {cat}")
    if data["categories"]:
        print("categories:")
        for cat in data["categories"]:
            print(f"  {cat['name']:<{width}}  {format_duration(cat['seconds']):>12}  {cat['share'] * 100:5.1f}%")
    return 0


def cmd_status(args) -> int:
    status = daemon_status(time.time())
    if args.json:
        print(json.dumps(status))
    else:
        if status["running"]:
            print(f"running: {status['state']}" + (f" ({status['current_app']})" if status["current_app"] else ""))
            if not status.get("idle_detection"):
                print("idle detection is off (idle_timeout = 0 or swayidle missing)")
        else:
            print("not running")
    return 0 if status["running"] else 3


def cmd_config(args) -> int:
    if args.action == "path":
        print(paths.config_file())
        return 0
    cfg = config_mod.load()
    if args.action == "get":
        if args.key:
            if args.key not in config_mod.FIELD_TYPES:
                print(f"unknown key {args.key}", file=sys.stderr)
                return 2
            value = getattr(cfg, args.key)
            print(json.dumps(value))
        else:
            print(json.dumps(cfg.__dict__))
        return 0
    # set
    if args.key not in config_mod.FIELD_TYPES or args.value is None:
        print("usage: screentime config set KEY VALUE  (keys: " + ", ".join(config_mod.FIELD_TYPES) + ")",
              file=sys.stderr)
        return 2
    try:
        value = config_mod.parse_value(args.key, args.value)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    setattr(cfg, args.key, value)
    cfg.validate()
    current = config_mod.load()
    if getattr(current, args.key) != getattr(cfg, args.key):
        config_mod.set_value(args.key, getattr(cfg, args.key))
    return 0


def cmd_categories(args) -> int:
    path = paths.categories_file()
    if args.action == "path":
        print(path)
        return 0
    store = _open_store()
    resolver = _resolver(store)
    seen = [row[0] for row in store.known_apps()] if store else []
    existing = path.read_text() if path.exists() else None
    try:
        text, added = categories_mod.generate(resolver, existing, seen)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.dry_run:
        sys.stdout.write(text)
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"{path}: {added} entries added")
    return 0


def cmd_apps(args) -> int:
    store = _open_store()
    if store is None:
        print("no data yet", file=sys.stderr)
        return 1
    resolver = _resolver(store)
    categorizer = categories_mod.Categorizer(categories_mod.load())
    rows = []
    for app_id, exe, first_seen, last_seen in store.known_apps():
        info = resolver.resolve(app_id)
        rows.append({
            **info.as_dict(),
            "category": categorizer.category(app_id, info.desktop_id),
            "exe": exe,
            "last_seen": last_seen,
        })
    if args.unresolved:
        rows = [r for r in rows if r["desktop_id"] is None]
    if args.json:
        print(json.dumps(rows))
        return 0
    for r in rows:
        print(f"{r['app_id']:40} {r['name']:28} desktop={r['desktop_id'] or '-':32} category={r['category'] or '-'}")
    return 0


def cmd_log(args) -> int:
    store = _open_store()
    if store is None:
        print("no data yet", file=sys.stderr)
        return 1
    for iid, app_id, start, end, title in reversed(store.recent(args.limit)):
        s = dt.datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M:%S")
        e = dt.datetime.fromtimestamp(end).strftime("%H:%M:%S")
        extra = f"  {title}" if title else ""
        print(f"{iid:7} {s} – {e} {format_duration(end - start):>10}  {app_id}{extra}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="screentime", description="Screen Time for niri")
    p.add_argument("--version", action="version", version=f"screentime {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("daemon", help="run the tracker (normally via systemd)")
    d.add_argument("-v", "--verbose", action="store_true")
    d.set_defaults(func=cmd_daemon)

    s = sub.add_parser("summary", help="usage summary (what the DMS plugin shows)")
    s.add_argument("--range", choices=["today", "day", "week", "month"], default="day")
    s.add_argument("--date", help="any date inside the range (YYYY-MM-DD), default today")
    s.add_argument("--json", action="store_true")
    s.add_argument("--limit", type=int, default=15, help="apps shown in text mode")
    s.set_defaults(func=cmd_summary)

    st = sub.add_parser("status", help="is the daemon running, and what is it counting")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_status)

    c = sub.add_parser("config", help="read or change ~/.config/screentime/config.toml")
    c.add_argument("action", choices=["get", "set", "path"])
    c.add_argument("key", nargs="?")
    c.add_argument("value", nargs="?")
    c.set_defaults(func=cmd_config)

    cat = sub.add_parser("categories", help="manage the app -> category mapping")
    cat.add_argument("action", choices=["generate", "path"])
    cat.add_argument("--dry-run", action="store_true", help="print instead of writing")
    cat.set_defaults(func=cmd_categories)

    a = sub.add_parser("apps", help="app_ids seen so far and how they resolve")
    a.add_argument("--unresolved", action="store_true", help="only apps without a desktop file")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_apps)

    lg = sub.add_parser("log", help="most recent raw intervals (debugging)")
    lg.add_argument("--limit", type=int, default=30)
    lg.set_defaults(func=cmd_log)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
