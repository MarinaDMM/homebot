"""Trash & recycling pickup schedule for the Netherlands via mijnafvalwijzer.nl."""

import logging
from datetime import date, datetime
import requests

log = logging.getLogger(__name__)

ENDPOINT = "https://api.mijnafvalwijzer.nl/webservices/appsinput/?method=postcodecheck&postcode={postcode}&street=&huisnummer={hnr}&toevoeging=&platform=phone&langs=nl"

FRACTION_LABEL = {
    "gft": "🌱 GFT (green)",
    "pmd": "♻️ PMD (plastic/metal)",
    "papier": "📄 Paper",
    "restafval": "🗑 Restafval",
    "rest": "🗑 Restafval",
    "kerstboom": "🎄 Christmas trees",
}


def fetch_pickups(postcode: str, house_number) -> list[dict]:
    url = ENDPOINT.format(postcode=str(postcode).replace(" ", "").upper(), hnr=house_number)
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("afvalwijzer fetch failed: %s", e)
        return []

    pickups = []
    today = date.today()
    upcoming = data.get("ophaaldagen", {}).get("data", [])
    for item in upcoming:
        try:
            d = datetime.strptime(item["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if d < today:
            continue
        fr = (item.get("nameType") or "").lower()
        pickups.append({
            "date": d,
            "fraction": fr,
            "label": FRACTION_LABEL.get(fr, fr.title() or "Pickup"),
        })
    pickups.sort(key=lambda p: p["date"])
    return pickups


def format_today_tomorrow(postcode: str, house_number) -> str | None:
    pickups = fetch_pickups(postcode, house_number)
    if not pickups:
        return None
    today = date.today()
    next_up = pickups[0]
    delta = (next_up["date"] - today).days
    if delta == 0:
        return f"🚛 Pickup *today*: {next_up['label']}"
    if delta == 1:
        return f"🚛 Pickup *tomorrow*: {next_up['label']} — put it out tonight"
    return None


def format_upcoming(postcode: str, house_number, n: int = 4) -> str:
    pickups = fetch_pickups(postcode, house_number)[:n]
    if not pickups:
        return "No upcoming pickups found."
    lines = ["📅 *Upcoming pickups:*"]
    for p in pickups:
        lines.append(f"  {p['date'].strftime('%a %d %b')} — {p['label']}")
    return "\n".join(lines)
