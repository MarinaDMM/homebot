"""Gmail polling: list recent messages, decode bodies."""

import base64
import logging
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from bs4 import BeautifulSoup

from .google_auth import get_credentials

log = logging.getLogger(__name__)


def _service():
    return build("gmail", "v1", credentials=get_credentials(), cache_discovery=False)


def list_recent_messages(*, labels: list[str], lookback_days: int = 1, max_results: int = 30) -> list[str]:
    svc = _service()
    after = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp()
    query = f"after:{int(after)}"
    resp = svc.users().messages().list(
        userId="me",
        labelIds=labels or None,
        q=query,
        maxResults=max_results,
    ).execute()
    return [m["id"] for m in resp.get("messages", [])]


def get_message(message_id: str) -> dict:
    svc = _service()
    msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    return {
        "id": msg["id"],
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "date": headers.get("date", ""),
        "snippet": msg.get("snippet", ""),
        "body": _extract_body(msg["payload"]),
    }


def _extract_body(payload: dict) -> str:
    parts = [payload]
    plain_chunks, html_chunks = [], []
    while parts:
        part = parts.pop(0)
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data:
            decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            if mime == "text/plain":
                plain_chunks.append(decoded)
            elif mime == "text/html":
                html_chunks.append(decoded)
        for sub in part.get("parts", []) or []:
            parts.append(sub)
    if plain_chunks:
        return "\n".join(plain_chunks).strip()
    if html_chunks:
        soup = BeautifulSoup("\n".join(html_chunks), "html.parser")
        return soup.get_text("\n").strip()
    return ""
