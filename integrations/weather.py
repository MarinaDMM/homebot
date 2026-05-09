"""Weather + alerts for the Netherlands via Buienradar (no API key)."""

import logging
import requests

log = logging.getLogger(__name__)

BUIENRADAR_FEED = "https://data.buienradar.nl/2.0/feed/json"


def _haversine_km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, asin, sqrt
    r = 6371
    dlat = radians(lat2 - lat1); dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def fetch_weather(lat: float, lon: float) -> dict:
    try:
        r = requests.get(BUIENRADAR_FEED, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("buienradar fetch failed: %s", e)
        return {"error": str(e)}

    stations = data.get("actual", {}).get("stationmeasurements", [])
    if not stations:
        return {"error": "no station data"}

    nearest = min(
        stations,
        key=lambda s: _haversine_km(lat, lon, float(s.get("lat", 0)), float(s.get("lon", 0))),
    )
    forecast_days = data.get("forecast", {}).get("fivedayforecast", [])
    today = forecast_days[0] if forecast_days else {}
    warnings = data.get("forecast", {}).get("weatherreport", {})

    return {
        "now": {
            "temp": nearest.get("temperature"),
            "condition": nearest.get("weatherdescription"),
            "wind_kmh": nearest.get("windspeedBft"),
            "station": nearest.get("stationname"),
        },
        "today": {
            "min": today.get("mintemperature"),
            "max": today.get("maxtemperature"),
            "rain_chance_pct": today.get("rainChance"),
            "wind": today.get("windDirection"),
            "summary": today.get("weatherdescription"),
        },
        "report": {
            "title": warnings.get("title"),
            "summary": warnings.get("summary"),
        },
    }


def format_weather(w: dict) -> str:
    if "error" in w:
        return f"⚠️ Weather: {w['error']}"
    now = w.get("now", {}) or {}
    today = w.get("today", {}) or {}
    lines = [
        f"🌤 *Weather* ({now.get('station', 'NL')})",
        f"  Now: {now.get('temp', '?')}°C — {now.get('condition', '?')}",
        f"  Today: {today.get('min', '?')}–{today.get('max', '?')}°C, "
        f"rain {today.get('rain_chance_pct', '?')}%",
    ]
    if (w.get("report") or {}).get("title"):
        lines.append(f"  ⚠️ {w['report']['title']}")
    return "\n".join(lines)
