"""Natural-language reminder parser.

Handles inputs like:
    'every Tuesday at 19:00 take out the trash'
    'every weekday 9am standup'
    'tomorrow 14:30 dentist'
    'in 2 hours water plants'
    'on 2026-05-12 16:00 pick up package'

Returns a tuple (kind, spec, text) where:
    kind == 'cron' and spec is a 5-field cron string (m h dom mon dow), or
    kind == 'once' and spec is an ISO datetime string.
"""

import re
from datetime import datetime, timedelta
from dateutil import parser as dateparser

DAY_NUM = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DAY_NUM.update({
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
})


class ParseError(Exception):
    pass


def parse(text: str) -> tuple[str, str, str]:
    raw = text.strip()
    low = raw.lower()

    # -- recurring: every <day(s)> at <time> ... --
    m = re.match(
        r"every\s+(weekday|day|"
        r"(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*"
        r"(?:\s*[,&/]\s*(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*)*)"
        r"\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+(.+)",
        low,
    )
    if m:
        days_word, hh, mm, ampm, rest = m.groups()
        hour = _to_24h(int(hh), ampm)
        minute = int(mm) if mm else 0
        dow = _resolve_dow(days_word)
        cron = f"{minute} {hour} * * {dow}"
        return "cron", cron, _restore_case(raw, rest)

    # -- relative: in N (minutes|hours|days) ... --
    m = re.match(r"in\s+(\d+)\s+(minute|min|hour|hr|day)s?\s+(.+)", low)
    if m:
        n, unit, rest = m.groups()
        n = int(n)
        delta = {
            "minute": timedelta(minutes=n), "min": timedelta(minutes=n),
            "hour": timedelta(hours=n), "hr": timedelta(hours=n),
            "day": timedelta(days=n),
        }[unit]
        when = datetime.now() + delta
        return "once", when.replace(microsecond=0).isoformat(), _restore_case(raw, rest)

    # -- one-off: tomorrow / today / on <date> [at] HH:MM ... --
    m = re.match(
        r"(tomorrow|today|on\s+\S+)\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+(.+)",
        low,
    )
    if m:
        whenword, hh, mm, ampm, rest = m.groups()
        hour = _to_24h(int(hh), ampm)
        minute = int(mm) if mm else 0
        if whenword == "today":
            base = datetime.now()
        elif whenword == "tomorrow":
            base = datetime.now() + timedelta(days=1)
        else:  # 'on <date>'
            datestr = whenword.split(None, 1)[1]
            base = dateparser.parse(datestr, dayfirst=True)
        when = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return "once", when.isoformat(), _restore_case(raw, rest)

    # Last-ditch: try dateutil on the whole thing.
    try:
        when = dateparser.parse(raw, fuzzy=True, dayfirst=True)
        rest = re.sub(r"\s+", " ",
                      re.sub(r"\b(today|tomorrow|on|at|am|pm|\d{1,2}(:\d{2})?)\b", "", raw, flags=re.I)
                      ).strip()
        if when and rest:
            return "once", when.replace(second=0, microsecond=0).isoformat(), rest
    except Exception:
        pass

    raise ParseError(
        "Couldn't parse that. Try formats like:\n"
        "• every Tuesday at 19:00 take out trash\n"
        "• every weekday 9am standup\n"
        "• tomorrow 14:30 dentist\n"
        "• in 2 hours water plants"
    )


def _to_24h(hour: int, ampm: str | None) -> int:
    if not ampm:
        return hour
    ampm = ampm.lower()
    if ampm == "am":
        return 0 if hour == 12 else hour
    return 12 if hour == 12 else hour + 12


def _resolve_dow(word: str) -> str:
    if word == "day":
        return "*"
    if word == "weekday":
        return "1-5"
    parts = re.split(r"[,&/\s]+", word.strip())
    nums = sorted({DAY_NUM[p[:3]] for p in parts if p[:3] in DAY_NUM})
    cron_dow = sorted({(d + 1) % 7 for d in nums})
    return ",".join(str(d) for d in cron_dow)


def _restore_case(raw: str, lowered_rest: str) -> str:
    idx = raw.lower().rfind(lowered_rest.strip())
    return raw[idx:].strip() if idx >= 0 else lowered_rest.strip()
