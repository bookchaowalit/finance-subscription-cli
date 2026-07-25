"""
Gmail API adapter — READ ONLY.

Never labels, stars, archives, deletes, or modifies messages.
Uses Solo Empire OAuth via infra_bridge only.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from ..infra_bridge import api_request, google_access_token

# Query tuned for subscription / billing signals (not general inbox noise)
DEFAULT_QUERY_PARTS = [
    "(invoice OR receipt OR renewal OR subscription OR trial OR membership",
    "OR \"billing statement\" OR \"payment received\" OR \"your plan\"",
    "OR \"price increase\" OR \"will renew\" OR unsubscribe OR \"cancel anytime\")",
]


@dataclass
class MessageMeta:
    """Minimal message payload — no full body retained in registry."""

    id: str
    thread_id: str
    from_address: str
    from_name: str
    subject: str
    date: str | None
    snippet: str
    labels: list[str]


class GmailReadOnlyAdapter:
    """Read-only Gmail client for subscription scanning."""

    BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

    def __init__(self, token: str | None = None):
        self.token = token or google_access_token()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def profile(self) -> dict[str, Any]:
        return api_request(f"{self.BASE}/profile", headers=self._headers())

    def search_message_ids(
        self,
        days: int = 365,
        max_results: int = 200,
        extra_query: str = "",
    ) -> list[str]:
        after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y/%m/%d")
        q = f'after:{after} {" ".join(DEFAULT_QUERY_PARTS)}'
        if extra_query:
            q = f"{q} {extra_query}"
        ids: list[str] = []
        page_token = None
        while len(ids) < max_results:
            params: dict[str, Any] = {
                "q": q,
                "maxResults": min(100, max_results - len(ids)),
            }
            if page_token:
                params["pageToken"] = page_token
            url = f"{self.BASE}/messages?{urllib.parse.urlencode(params)}"
            resp = api_request(url, headers=self._headers())
            for m in resp.get("messages", []) or []:
                ids.append(m["id"])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return ids

    def get_message_meta(self, message_id: str) -> MessageMeta | None:
        """Fetch metadata + snippet only (format=metadata)."""
        params = urllib.parse.urlencode(
            {
                "format": "metadata",
                "metadataHeaders": ["From", "Subject", "Date", "List-Unsubscribe"],
            },
            doseq=True,
        )
        # urllib doseq for repeated keys is awkward; build manually
        url = (
            f"{self.BASE}/messages/{message_id}"
            f"?format=metadata"
            f"&metadataHeaders=From&metadataHeaders=Subject"
            f"&metadataHeaders=Date&metadataHeaders=List-Unsubscribe"
        )
        try:
            msg = api_request(url, headers=self._headers())
        except Exception:
            return None

        headers = {
            h["name"]: h["value"]
            for h in (msg.get("payload") or {}).get("headers", [])
        }
        from_raw = headers.get("From", "")
        name, addr = _parse_from(from_raw)
        date_raw = headers.get("Date")
        date_iso = None
        if date_raw:
            try:
                date_iso = parsedate_to_datetime(date_raw).date().isoformat()
            except Exception:
                date_iso = date_raw[:16]

        # List-Unsubscribe often has <https://...>
        unsub = headers.get("List-Unsubscribe", "")
        snippet = (msg.get("snippet") or "")[:280]
        if unsub and "http" in unsub.lower():
            snippet = f"{snippet} | List-Unsubscribe: {unsub[:120]}"

        return MessageMeta(
            id=msg["id"],
            thread_id=msg.get("threadId", ""),
            from_address=addr,
            from_name=name,
            subject=headers.get("Subject", "") or "",
            date=date_iso,
            snippet=snippet,
            labels=msg.get("labelIds") or [],
        )

    def fetch_subscription_candidates(
        self,
        days: int = 365,
        max_results: int = 200,
    ) -> list[MessageMeta]:
        ids = self.search_message_ids(days=days, max_results=max_results)
        out: list[MessageMeta] = []
        for mid in ids:
            meta = self.get_message_meta(mid)
            if meta:
                out.append(meta)
        return out


def _parse_from(raw: str) -> tuple[str, str]:
    raw = (raw or "").strip()
    m = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', raw)
    if m:
        return m.group(1).strip(), m.group(2).strip().lower()
    if "@" in raw:
        return "", raw.strip("<> ").lower()
    return raw, ""
