"""Aggregate stored intervals into the summary JSON consumed by the UI.

Intervals are stored as UTC epoch ranges and are only split at query time,
along *local* day and hour boundaries (honouring DST and day_start_hour).
"""

import bisect
import datetime as dt
import json
import os
import time
from collections import defaultdict

from . import paths
from .apps import Resolver
from .categories import Categorizer

DAY = dt.timedelta(days=1)
JSON_VERSION = 1


# -- calendar helpers --------------------------------------------------------


def day_start(d: dt.date, start_hour: int) -> float:
    # Naive datetimes are local time; .timestamp() applies the right DST offset.
    return dt.datetime(d.year, d.month, d.day, start_hour).timestamp()


def logical_date(ts: float, start_hour: int) -> dt.date:
    local = dt.datetime.fromtimestamp(ts)
    if local.hour < start_hour:
        return local.date() - DAY
    return local.date()


def range_days(kind: str, anchor: dt.date) -> list[dt.date]:
    if kind == "day":
        return [anchor]
    if kind == "week":
        monday = anchor - dt.timedelta(days=anchor.weekday())
        return [monday + dt.timedelta(days=i) for i in range(7)]
    if kind == "month":
        first = anchor.replace(day=1)
        nxt = (first + dt.timedelta(days=32)).replace(day=1)
        return [first + dt.timedelta(days=i) for i in range((nxt - first).days)]
    raise ValueError(f"unknown range {kind!r}")


def shift_anchor(kind: str, anchor: dt.date, step: int) -> dt.date:
    if kind == "day":
        return anchor + dt.timedelta(days=step)
    if kind == "week":
        return anchor + dt.timedelta(days=7 * step)
    month = anchor.month - 1 + step
    year = anchor.year + month // 12
    return dt.date(year, month % 12 + 1, 1)


# -- daemon status -------------------------------------------------------------


def daemon_status(now: float) -> dict:
    try:
        status = json.loads(paths.status_file().read_text())
    except (OSError, ValueError):
        return {"running": False, "state": "stopped", "current_app": None}
    alive = True
    try:
        os.kill(int(status.get("pid", 0)), 0)
    except (OSError, ValueError):
        alive = False
    fresh = now - float(status.get("updated_at", 0)) < max(3 * status.get("heartbeat_seconds", 5), 15)
    running = alive and fresh
    return {
        "running": running,
        "state": status.get("state", "unknown") if running else "stopped",
        "current_app": status.get("current_app") if running else None,
        "current_interval_id": status.get("current_interval_id") if running else None,
        "idle_detection": status.get("idle_timeout", 0) > 0,
    }


# -- aggregation -------------------------------------------------------------


class Usage:
    """Seconds per (app, bucket) for a set of [start, end) buckets."""

    def __init__(self, intervals, bounds: list[float]):
        # bounds: sorted bucket edges; bucket i is [bounds[i], bounds[i+1])
        self.bounds = bounds
        self.by_bucket: list[dict[str, float]] = [defaultdict(float) for _ in range(len(bounds) - 1)]
        for app_id, start, end in intervals:
            if end <= bounds[0] or start >= bounds[-1]:
                continue
            i = max(0, bisect.bisect_right(bounds, start) - 1)
            while i < len(bounds) - 1 and bounds[i] < end:
                overlap = min(end, bounds[i + 1]) - max(start, bounds[i])
                if overlap > 0:
                    self.by_bucket[i][app_id] += overlap
                i += 1

    def total(self, i: int) -> float:
        return sum(self.by_bucket[i].values())


def summarize(store, kind: str = "day", anchor: dt.date | None = None, now: float | None = None,
              day_start_hour: int = 0, resolver: Resolver | None = None,
              categorizer: Categorizer | None = None, status: dict | None = None) -> dict:
    now = time.time() if now is None else now
    if kind == "today":
        kind = "day"
    today = logical_date(now, day_start_hour)
    anchor = anchor or today
    if anchor > today:
        anchor = today
    status = status if status is not None else daemon_status(now)
    resolver = resolver or Resolver(exes=store.app_exes() if store else {})
    categorizer = categorizer or Categorizer({})

    days = range_days(kind, anchor)
    if kind == "day":
        history = [anchor - dt.timedelta(days=6 - i) for i in range(7)]
        baseline = [anchor - dt.timedelta(days=7 - i) for i in range(7)]
    else:
        history = days
        prev = range_days(kind, shift_anchor(kind, anchor, -1))
        baseline = prev
    all_days = sorted(set(days) | set(history) | set(baseline))
    # Contiguous day edges from the first to the last needed day.
    span = [all_days[0] + dt.timedelta(days=i) for i in range((all_days[-1] - all_days[0]).days + 1)]
    day_edges = [day_start(d, day_start_hour) for d in span] + [day_start(span[-1] + DAY, day_start_hour)]
    day_index = {d: i for i, d in enumerate(span)}

    intervals = []
    if store is not None:
        live_id = status.get("current_interval_id") if status.get("state") == "active" else None
        for iid, app_id, start, end in store.intervals_between(day_edges[0], day_edges[-1]):
            if iid == live_id:
                end = max(end, now)  # the open interval is flushed only every heartbeat
            end = min(end, now)
            if end > start:
                intervals.append((app_id, start, end))
    per_day = Usage(intervals, day_edges)

    def day_total(d: dt.date) -> float:
        return per_day.total(day_index[d])

    # Totals per app over the selected range.
    app_secs: dict[str, float] = defaultdict(float)
    for d in days:
        for app_id, secs in per_day.by_bucket[day_index[d]].items():
            app_secs[app_id] += secs
    total = sum(app_secs.values())

    # Comparison against the baseline (7 days before for "day", the previous
    # period for week/month; days without data count as zero).
    baseline_avg = sum(day_total(d) for d in baseline) / len(baseline)
    elapsed = [d for d in days if d <= today]
    compare = total if kind == "day" else (total / len(elapsed) if elapsed else 0)
    vs_pct = round((compare - baseline_avg) / baseline_avg * 100) if baseline_avg >= 60 else None

    # Chart buckets.
    if kind == "day":
        base = dt.datetime(anchor.year, anchor.month, anchor.day, day_start_hour)
        hour_starts = [base + dt.timedelta(hours=h) for h in range(25)]
        edges = [h.timestamp() for h in hour_starts]
        hourly = Usage(intervals, edges)
        current_hour = dt.datetime.fromtimestamp(now).replace(minute=0, second=0, microsecond=0)
        buckets = [
            {
                "key": hour_starts[i].strftime("%Y-%m-%dT%H"),
                "hour": hour_starts[i].hour,
                "seconds": round(hourly.total(i)),
                "is_current": hour_starts[i] == current_hour,
                "is_future": edges[i] > now,
            }
            for i in range(24)
        ]
        chart = {"unit": "hour", "max_seconds": 3600, "buckets": buckets}
    else:
        buckets = [
            {
                "key": d.isoformat(),
                "date": d.isoformat(),
                "weekday": d.isoweekday(),
                "seconds": round(day_total(d)),
                "is_current": d == today,
                "is_future": d > today,
            }
            for d in days
        ]
        chart = {"unit": "day", "max_seconds": 86400, "buckets": buckets}

    # Apps, categories.
    apps = []
    cat_secs: dict[str, float] = defaultdict(float)
    cat_apps: dict[str, list[str]] = defaultdict(list)
    cat_is_app: dict[str, bool] = {}
    for app_id, secs in sorted(app_secs.items(), key=lambda kv: -kv[1]):
        if secs < 1:
            continue
        info = resolver.resolve(app_id)
        category = categorizer.category(app_id, info.desktop_id)
        apps.append({
            **info.as_dict(),
            "category": category,
            "seconds": round(secs),
            "share": secs / total if total else 0,
            "history": [round(per_day.by_bucket[day_index[d]].get(app_id, 0)) for d in history],
        })
        key = category or info.name
        cat_secs[key] += secs
        cat_apps[key].append(app_id)
        cat_is_app[key] = cat_is_app.get(key, True) and category is None
    categories = [
        {
            "name": name,
            "seconds": round(secs),
            "share": secs / total if total else 0,
            "is_app": cat_is_app[name],
            "apps": cat_apps[name],
        }
        for name, secs in sorted(cat_secs.items(), key=lambda kv: -kv[1])
    ]

    first = store.first_start() if store is not None else None
    first_date = logical_date(first, day_start_hour) if first else today
    prev_anchor = shift_anchor(kind, anchor, -1)
    next_anchor = shift_anchor(kind, anchor, 1)
    return {
        "version": JSON_VERSION,
        "generated_at": now,
        "daemon": status,
        "range": {
            "kind": kind,
            "anchor": anchor.isoformat(),
            "start": days[0].isoformat(),
            "end": days[-1].isoformat(),
            "today": today.isoformat(),
            "is_current": today in days,
            "prev": prev_anchor.isoformat() if range_days(kind, prev_anchor)[-1] >= first_date else None,
            "next": (next_anchor if next_anchor <= today else today).isoformat() if today not in days else None,
            "elapsed_days": len(elapsed),
        },
        "total_seconds": round(total),
        "average_seconds": round(baseline_avg),
        "compare_seconds": round(compare),
        "vs_average_pct": vs_pct,
        "chart": chart,
        "history_dates": [d.isoformat() for d in history],
        "apps": apps,
        "categories": categories,
        "first_date": first_date.isoformat(),
    }


def format_duration(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    if minutes < 1:
        return "< 1 min" if seconds > 0 else "0 min"
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours} h {minutes} min"
    if hours:
        return f"{hours} h"
    return f"{minutes} min"
