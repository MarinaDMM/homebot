"""Weather + alerts for the Netherlands via Buienradar (no API key)."""

import logging
import requests

log = logging.getLogger(__name__)

BUIENRADAR_FEED = "https://data.buienradar.nl/2.0/feed/json"

# Buienradar returns Dutch descriptions; map them to English.
_NL_TO_EN: dict[str, str] = {
    "Zonnig": "Sunny",
    "Licht bewolkt": "Partly cloudy",
    "Halfbewolkt": "Partly cloudy",
    "Bewolkt": "Cloudy",
    "Zwaar bewolkt": "Overcast",
    "Mix van opklaringen en middelbare of lage bewolking": "Partly cloudy",
    "Licht bewolkt met lichte regen": "Partly cloudy, light rain",
    "Bewolkt met lichte regen": "Cloudy, light rain",
    "Lichte regen": "Light rain",
    "Regen": "Rain",
    "Zware regen": "Heavy rain",
    "Buien": "Showers",
    "Onweer": "Thunderstorm",
    "Mist": "Fog",
    "Sneeuw": "Snow",
    "IJzel": "Freezing rain",
    "Hagel": "Hail",
    "Zwaar bewolkt met regen": "Overcast, rain",
    "Zwaar bewolkt met buien": "Overcast, showers",
    "Komende week frisser en licht wisselvallig": "Cooler and unsettled next week",
}


def _translate(description: str | None) -> str:
    if not description:
        return "Unknown"
    return _NL_TO_EN.get(description, description)


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

    # Prefer stations that report temperature; some coastal/wind stations omit it.
    temp_stations = [s for s in stations if s.get("temperature") is not None]
    pool = temp_stations or stations
    nearest = min(
        pool,
        key=lambda s: _haversine_km(lat, lon, float(s.get("lat", 0)), float(s.get("lon", 0))),
    )
    forecast_days = data.get("forecast", {}).get("fivedayforecast", [])
    today = forecast_days[0] if forecast_days else {}
    warnings = data.get("forecast", {}).get("weatherreport", {})

    return {
        "now": {
            "temp": nearest.get("temperature"),
            "condition": _translate(nearest.get("weatherdescription")),
            "station": nearest.get("stationname"),
        },
        "today": {
            "min": today.get("mintemperature"),
            "max": today.get("maxtemperature"),
            "rain_chance_pct": today.get("rainChance"),
            "summary": _translate(today.get("weatherdescription")),
        },
        "report": {
            "title": _translate(warnings.get("title")),
        },
    }


def format_weather(w: dict) -> str:
    if "error" in w:
        return f"⚠️ Weather: {w['error']}"
    now = w.get("now", {}) or {}
    today = w.get("today", {}) or {}
    temp = now.get("temp")
    temp_str = f"{temp}°C" if temp is not None else "?"
    lines = [
        f"🌤 *Weather* ({now.get('station', 'NL')})",
        f"  Now: {temp_str} — {now.get('condition', '?')}",
        f"  Today: {today.get('min', '?')}–{today.get('max', '?')}°C, "
        f"rain {today.get('rain_chance_pct', '?')}%",
    ]
    title = (w.get("report") or {}).get("title")
    if title and title != "Unknown":
        lines.append(f"  ⚠️ {title}")
    return "\n".join(lines)
