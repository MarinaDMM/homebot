"""Google Calendar: list today's events, create new ones."""

import logging
from datetime import date, datetime, time, timedelta, timezone

from googleapiclient.discovery import build

from .google_auth import get_credentials

log = logging.getLogger(__name__)

LOCAL_TZ = "Europe/Amsterdam"


def _service():
    return build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)


def list_today_events(calendar_id: str = "primary") -> list[dict]:
    svc = _service()
    today = date.today()
    start = datetime.combine(today, time.min).astimezone(timezone.utc).isoformat()
    end = datetime.combine(today, time.max).astimezone(timezone.utc).isoformat()
    resp = svc.events().list(
        calendarId=calendar_id,
        timeMin=start, timeMax=end,
        singleEvents=True, orderBy="startTime",
    ).execute()
    return resp.get("items", [])


def create_event(
    calendar_id: str,
    summary: str,
    start: datetime,
    end: datetime,
    *,
    description: str | None = None,
    location: str | None = None,
) -> dict:
    svc = _service()
    body = {
        "summary": summary,
        "start": {"dateTime": start.isoformat(), "timeZone": LOCAL_TZ},
        "end":   {"dateTime": end.isoformat(),   "timeZone": LOCAL_TZ},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    return svc.events().insert(calendarId=calendar_id, body=body).execute()


def format_today_events(events: list[dict]) -> str:
    if not events:
        return "📅 No events on the calendar today."
    lines = ["📅 *Today:*"]
    for e in events[:8]:
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date") or "?"
        if "T" in start:
            t = start.split("T", 1)[1][:5]
            lines.append(f"  {t} — {e.get('summary', '(no title)')}")
        else:
            lines.append(f"  All day — {e.get('summary', '(no title)')}")
    return "\n".join(lines)
