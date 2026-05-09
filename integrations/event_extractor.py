"""Use Claude to spot calendar-worthy events in an email."""

import json
import logging
from datetime import datetime
from anthropic import Anthropic

log = logging.getLogger(__name__)

PROMPT = """You analyze an email to decide whether it describes a single calendar event the recipient should add to their schedule.

INCLUDE:
- Flight, train, and hotel reservations
- Restaurant bookings
- Doctor / dentist appointments
- Meeting invites with a clear date+time (only if not already a calendar invite)
- Concert / event tickets
- Package deliveries with a specific time window

EXCLUDE:
- Marketing newsletters with mentions of dates
- Emails about events that already happened
- Emails clearly already containing a calendar invite (.ics)
- Vague references ("let's grab coffee sometime")

Today is {today}. The recipient is in the Europe/Amsterdam timezone.

Respond with strict JSON. Use this schema:

If event found:
{{"event": true, "summary": str, "start_iso": "YYYY-MM-DDTHH:MM:SS", "end_iso": "YYYY-MM-DDTHH:MM:SS", "location": str|null, "confidence": float (0..1), "reason": str}}

If no event:
{{"event": false, "reason": str}}

EMAIL:
Subject: {subject}
From: {sender}
Date: {date}

{body}
"""


def extract_event(api_key: str, model: str, email: dict) -> dict:
    client = Anthropic(api_key=api_key)
    prompt = PROMPT.format(
        today=datetime.now().strftime("%Y-%m-%d %A"),
        subject=email.get("subject", ""),
        sender=email.get("from", ""),
        date=email.get("date", ""),
        body=(email.get("body") or email.get("snippet", ""))[:6000],
    )
    msg = client.messages.create(
        model=model,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON: %s", raw[:200])
        return {"event": False, "reason": "parse_error"}
