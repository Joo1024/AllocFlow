from datetime import date, timedelta
from functools import lru_cache

import exchange_calendars as xcals


@lru_cache(maxsize=64)
def calendar(name: str, start_year: int, end_year: int):
    return xcals.get_calendar(name, start=f"{start_year}-01-01", end=f"{end_year}-12-31")


def sessions(name: str, start: date, end: date) -> tuple[date, ...]:
    cal = calendar(name, start.year - 1, end.year + 1)
    return tuple(t.date() for t in cal.sessions_in_range(str(start), str(end)))


def next_session(name: str, day: date, delay: int = 0) -> date:
    candidates = sessions(name, day, day + timedelta(days=366))
    if delay >= len(candidates):
        raise ValueError(f"cannot resolve session for {name}/{day}/{delay}")
    return candidates[delay]


def month_ends(name: str, start: date, end: date) -> set[date]:
    full = sessions(name, date(start.year, start.month, 1), date(end.year + 1, 1, 1))
    last = {}
    for day in full:
        last[(day.year, day.month)] = day
    return {d for d in last.values() if start <= d <= end}
