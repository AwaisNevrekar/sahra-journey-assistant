"""Simulated airport clock (Asia/Dubai). Stored in the DB so the UI, autopilot and tests share one time."""
from datetime import datetime, timedelta, timezone

from . import db

TZ = timezone(timedelta(hours=4))


def now() -> datetime:
    v = db.get_setting("sim_now")
    if v:
        return datetime.fromisoformat(v)
    return datetime.now(TZ).replace(microsecond=0)


def set_now(dt: datetime):
    db.set_setting("sim_now", dt.replace(microsecond=0).isoformat())


def parse(s):
    if s is None or s == "":
        return None
    if isinstance(s, datetime):
        return s
    return datetime.fromisoformat(str(s))


def hhmm(v) -> str:
    dt = parse(v)
    return dt.astimezone(TZ).strftime("%H:%M") if dt else "—"


def minutes_since(v) -> float:
    return round((now() - parse(v)).total_seconds() / 60, 1)
