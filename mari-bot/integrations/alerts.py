"""NL civic alerts via KNMI weather warnings (proxy for NL-Alert)."""

import logging
import requests

log = logging.getLogger(__name__)

KNMI_WAARSCHUWINGEN = "https://cdn.knmi.nl/knmi/json/page/weer/waarschuwingen_gevaarlijkweer/nederland_waarschuwingen.json"


def fetch_alerts() -> list[dict]:
    try:
        r = requests.get(KNMI_WAARSCHUWINGEN, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("KNMI fetch failed: %s", e)
        return []

    alerts = []
    for level in ("rood", "oranje", "geel"):
        block = data.get(level, {})
        for entry in block.get("waarschuwingen", []) or []:
            alerts.append({
                "level": level,
                "title": entry.get("titel") or entry.get("title"),
                "text": entry.get("tekst") or entry.get("text"),
                "from": entry.get("vanaf"),
                "until": entry.get("tot"),
            })
    return alerts


def format_alerts(alerts: list[dict]) -> str:
    if not alerts:
        return ""
    lvl_emoji = {"rood": "🔴", "oranje": "🟠", "geel": "🟡"}
    lines = ["⚠️ *Active KNMI alerts:*"]
    for a in alerts:
        lines.append(f"  {lvl_emoji.get(a['level'], '•')} {a['title']}")
    return "\n".join(lines)
