"""Organisation clock and working-time calendar. Read-only helpers.

Demo orgs keep the deterministic as-of date (clock_mode "as_of"); private deployments use real time
(clock_mode "real") in the org's time zone. Working time follows the org's working-hours calendar and holidays."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_HOURS = {"start": "09:00", "end": "17:00", "days": [0, 1, 2, 3, 4]}


def tz(settings: dict) -> ZoneInfo:
    try:
        return ZoneInfo(settings.get("timezone") or "UTC")
    except Exception:  # noqa: BLE001 - an invalid zone must not take the app down
        return ZoneInfo("UTC")


def real_time(settings: dict) -> bool:
    return settings.get("clock_mode") == "real"


def today(settings: dict) -> date:
    if real_time(settings):
        return datetime.now(tz(settings)).date()
    return date.fromisoformat(settings["as_of_date"])


def now(settings: dict) -> datetime:
    """Real mode: wall clock. As-of mode: the as-of date at the end of the working day (deterministic)."""
    if real_time(settings):
        return datetime.now(timezone.utc)
    hours = settings.get("working_hours") or DEFAULT_HOURS
    end = time.fromisoformat(hours.get("end", "17:00"))
    return datetime.combine(today(settings), end, tzinfo=tz(settings)).astimezone(timezone.utc)


def _aware(v: datetime) -> datetime:
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def working_seconds(start: datetime, end: datetime, settings: dict) -> int:
    """Seconds of working time between two instants under the org calendar."""
    start, end = _aware(start), _aware(end)
    if end <= start:
        return 0
    zone = tz(settings)
    hours = settings.get("working_hours") or DEFAULT_HOURS
    open_t, close_t = time.fromisoformat(hours["start"]), time.fromisoformat(hours["end"])
    days = set(hours.get("days", DEFAULT_HOURS["days"]))
    holidays = {date.fromisoformat(d) for d in settings.get("holidays") or []}
    total = 0
    day = start.astimezone(zone).date()
    last = end.astimezone(zone).date()
    while day <= last:
        if day.weekday() in days and day not in holidays:
            w0 = datetime.combine(day, open_t, tzinfo=zone)
            w1 = datetime.combine(day, close_t, tzinfo=zone)
            a, b = max(w0, start), min(w1, end)
            if b > a:
                total += int((b - a).total_seconds())
        day += timedelta(days=1)
    return total


def working_days_between(start: date, end: date, settings: dict) -> int:
    """Working days after `start` up to and including `end`."""
    hours = settings.get("working_hours") or DEFAULT_HOURS
    days = set(hours.get("days", DEFAULT_HOURS["days"]))
    holidays = {date.fromisoformat(d) for d in settings.get("holidays") or []}
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() in days and d not in holidays:
            n += 1
    return n


def add_working_days(start: date, n: int, settings: dict) -> date:
    hours = settings.get("working_hours") or DEFAULT_HOURS
    days = set(hours.get("days", DEFAULT_HOURS["days"]))
    holidays = {date.fromisoformat(d) for d in settings.get("holidays") or []}
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() in days and d not in holidays:
            n -= 1
    return d


def task_clock(task, pauses: list, settings: dict) -> dict:
    """Working time a task has been open, excluding waiting intervals; whether it is waiting right now."""
    end = _aware(task.completed_at) if task.completed_at else now(settings)
    elapsed = working_seconds(task.created_at, end, settings)
    paused = 0
    waiting = None
    for p in pauses:
        p_end = _aware(p.resumed_at) if p.resumed_at else end
        paused += working_seconds(max(_aware(p.paused_at), _aware(task.created_at)), p_end, settings)
        if p.resumed_at is None:
            waiting = p.reason
    active = max(0, elapsed - paused)
    paused_days = round(paused / 3600 / _hours_per_day(settings))
    return {"working_hours": round(active / 3600, 2), "waiting_hours": round(paused / 3600, 2),
            "waiting": waiting is not None, "waiting_reason": waiting, "paused_working_days": paused_days}


def _hours_per_day(settings: dict) -> float:
    hours = settings.get("working_hours") or DEFAULT_HOURS
    a, b = time.fromisoformat(hours["start"]), time.fromisoformat(hours["end"])
    return max(1.0, (datetime.combine(date.min, b) - datetime.combine(date.min, a)).total_seconds() / 3600)
