"""Google Calendar read-only adapter for usage evidence."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .infra_bridge import api_request, google_access_token


@dataclass
class CalendarEventLite:
    id: str
    summary: str
    start: str | None
    end: str | None


class CalendarReadOnlyAdapter:
    BASE = "https://www.googleapis.com/calendar/v3"

    def __init__(self, token: str | None = None):
        self.token = token or google_access_token()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def list_events(
        self,
        days_back: int = 90,
        days_forward: int = 30,
        max_results: int = 250,
    ) -> list[CalendarEventLite]:
        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(days=days_back)).isoformat().replace("+00:00", "Z")
        time_max = (now + timedelta(days=days_forward)).isoformat().replace("+00:00", "Z")
        params = urllib.parse.urlencode(
            {
                "singleEvents": "true",
                "orderBy": "startTime",
                "timeMin": time_min,
                "timeMax": time_max,
                "maxResults": max_results,
            }
        )
        url = f"{self.BASE}/calendars/primary/events?{params}"
        try:
            resp = api_request(url, headers=self._headers())
        except Exception:  # noqa: BLE001 - calendar is optional enrichment; failure means no events
            return []

        events: list[CalendarEventLite] = []
        for item in resp.get("items", []) or []:
            start = (item.get("start") or {}).get("dateTime") or (item.get("start") or {}).get(
                "date"
            )
            end = (item.get("end") or {}).get("dateTime") or (item.get("end") or {}).get("date")
            events.append(
                CalendarEventLite(
                    id=item.get("id", ""),
                    summary=(item.get("summary") or "").strip(),
                    start=start,
                    end=end,
                )
            )
        return events

    def usage_hits_for_merchant(
        self,
        merchant: str,
        events: list[CalendarEventLite] | None = None,
    ) -> list[str]:
        """Return short usage signals if calendar titles mention merchant tokens."""
        events = events if events is not None else self.list_events()
        tokens = _merchant_tokens(merchant)
        hits: list[str] = []
        for ev in events:
            text = (ev.summary or "").lower()
            if any(t in text for t in tokens if len(t) >= 3):
                hits.append(f"calendar:{ev.summary[:80]}@{ev.start or '?'}")
        return hits


_STOP = {
    "inc",
    "llc",
    "ltd",
    "the",
    "com",
    "with",
    "from",
    "team",
    "via",
    "and",
    "for",
    "your",
    "mail",
    "email",
    "noreply",
    "notification",
}


def _merchant_tokens(merchant: str) -> list[str]:
    base = re_sub_non_alnum(merchant.lower())
    # Prefer distinctive tokens (len>=4) to avoid false calendar hits like "with"
    parts = [p for p in base.split() if p and len(p) >= 4 and p not in _STOP]
    if base:
        compact = base.replace(" ", "")
        if len(compact) >= 4:
            parts.append(compact)
    return list(dict.fromkeys(parts))


def re_sub_non_alnum(s: str) -> str:
    import re

    return re.sub(r"[^a-z0-9\s]", " ", s)
