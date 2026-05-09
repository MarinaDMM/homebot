"""Postcode → lat/lon via PDOK Locatieserver (NL official, free, no API key)."""

import logging
import requests

log = logging.getLogger(__name__)

PDOK_FREE = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"


class GeocodeError(RuntimeError):
    pass


def geocode_nl(postcode: str, house_number: int | str) -> dict:
    """Returns {lat, lon, address}. Raises GeocodeError if not found."""
    pc = postcode.replace(" ", "").upper()
    q = f"{pc} {house_number}"
    try:
        r = requests.get(
            PDOK_FREE,
            params={
                "q": q,
                "fq": "type:adres",
                "fl": "id,weergavenaam,centroide_ll",
                "rows": 1,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        raise GeocodeError(f"PDOK lookup failed: {e}") from e

    docs = data.get("response", {}).get("docs", [])
    if not docs:
        raise GeocodeError(f"No address found for '{q}'. Check postcode + house number.")

    doc = docs[0]
    # centroide_ll comes as 'POINT(lon lat)'
    pt = doc.get("centroide_ll", "")
    if not pt.startswith("POINT("):
        raise GeocodeError(f"Unexpected centroid format: {pt}")
    lon, lat = pt[len("POINT("):-1].split()
    return {
        "lat": float(lat),
        "lon": float(lon),
        "address": doc.get("weergavenaam", q),
    }
