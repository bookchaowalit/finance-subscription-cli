"""
Heuristic extractors for subscription billing signals.

Operates on MessageMeta only (subject + snippet + headers) — no full body storage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..gmail_adapter.client import MessageMeta

# Known SaaS / sub merchants → display names
KNOWN_MERCHANTS: dict[str, str] = {
    "notion.so": "Notion",
    "notion.com": "Notion",
    "vercel.com": "Vercel",
    "github.com": "GitHub",
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
    "claude.com": "Claude",
    "cursor.com": "Cursor",
    "cursor.sh": "Cursor",
    "figma.com": "Figma",
    "spotify.com": "Spotify",
    "netflix.com": "Netflix",
    "youtube.com": "YouTube",
    "google.com": "Google",
    "accounts.google.com": "Google",
    "apple.com": "Apple",
    "microsoft.com": "Microsoft",
    "adobe.com": "Adobe",
    "dropbox.com": "Dropbox",
    "1password.com": "1Password",
    "lastpass.com": "LastPass",
    "todoist.com": "Todoist",
    "linear.app": "Linear",
    "slack.com": "Slack",
    "zoom.us": "Zoom",
    "canva.com": "Canva",
    "udemy.com": "Udemy",
    "coursera.org": "Coursera",
    "chatgpt.com": "ChatGPT",
    "midjourney.com": "Midjourney",
    "runpod.io": "RunPod",
    "digitalocean.com": "DigitalOcean",
    "aws.amazon.com": "AWS",
    "cloudflare.com": "Cloudflare",
    "namecheap.com": "Namecheap",
    "godaddy.com": "GoDaddy",
    "shopify.com": "Shopify",
    "fastwork.co": "Fastwork",
    "upwork.com": "Upwork",
    "linkedin.com": "LinkedIn",
    "capacities.io": "Capacities",
    "craft.do": "Craft",
    "letterboxd.com": "Letterboxd",
    "crunchyroll.com": "Crunchyroll",
    "resend.com": "Resend",
    "kilocode.ai": "Kilo",
    "higgsfield.ai": "Higgsfield",
    "quillbot.com": "Quillbot",
    "creativefabrica.com": "Creative Fabrica",
    "substack.com": "Substack",
    "grammarly.com": "Grammarly",
    "notion.site": "Notion",
    "stripe.com": "Stripe",
    "paypal.com": "PayPal",
    "paddle.com": "Paddle",
    "ifttt.com": "IFTTT",
    "students.udemy.com": "Udemy",
    "email.claude.com": "Claude",
    "mail.crunchyroll.com": "Crunchyroll",
    "account.netflix.com": "Netflix",
}

EVENT_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    (
        "price_increase",
        re.compile(r"price\s+increase|raising\s+(our\s+)?prices|new\s+pricing", re.IGNORECASE),
        0.85,
    ),
    (
        "trial",
        re.compile(r"\bfree\s+trial\b|\btrial\s+ends?\b|\btrial\s+expir", re.IGNORECASE),
        0.8,
    ),
    (
        "renewal",
        re.compile(r"\brenew(s|al|ing)?\b|\bauto[- ]?renew\b|\bwill\s+renew\b", re.IGNORECASE),
        0.8,
    ),
    (
        "invoice",
        re.compile(r"\binvoice\b|\bbilling\s+statement\b", re.IGNORECASE),
        0.85,
    ),
    (
        "receipt",
        re.compile(
            r"\breceipt\b|\bpayment\s+received\b|\byour\s+payment\b|\bpaid\b",
            re.IGNORECASE,
        ),
        0.75,
    ),
    (
        "cancellation_link",
        re.compile(r"\bcancel\b|\bunsubscribe\b|\bmanage\s+subscription\b", re.IGNORECASE),
        0.55,
    ),
    (
        "payment",
        re.compile(r"\bsubscription\b|\bmembership\b|\byour\s+plan\b", re.IGNORECASE),
        0.5,
    ),
]

AMOUNT_RE = re.compile(
    r"(?P<currency>USD|THB|EUR|GBP|\$|฿|€|£)\s*(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)"
    r"|(?P<amount2>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\s*(?P<currency2>USD|THB|EUR|GBP)",
    re.IGNORECASE,
)

CYCLE_RE = re.compile(
    r"\b(monthly|annual|yearly|per\s+year|per\s+month|/mo|/yr|year(?:ly)?|month(?:ly)?)\b",
    re.IGNORECASE,
)

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


@dataclass
class ExtractedSignal:
    source_message_id: str
    merchant: str
    normalized_name: str
    event_type: str
    event_date: str | None
    amount: float | None
    currency: str | None
    billing_cycle: str | None
    snippet_evidence: str
    confidence: float
    cancellation_url: str | None
    from_address: str
    subject: str

    def to_evidence_dict(self) -> dict[str, Any]:
        return {
            "source_message_id": self.source_message_id,
            "event_type": self.event_type,
            "event_date": self.event_date,
            "amount": self.amount,
            "currency": self.currency,
            "snippet_evidence": self.snippet_evidence[:280],
            "confidence": round(self.confidence, 3),
            "cancellation_url": self.cancellation_url,
        }


def extract_signals_from_message(msg: MessageMeta) -> list[ExtractedSignal]:
    text = f"{msg.subject} {msg.snippet}"
    event_type, base_conf = _detect_event(text)
    merchant, normalized = _detect_merchant(msg.from_address, msg.from_name, msg.subject)
    if not merchant:
        return []

    # Known SaaS sender with weak keywords still counts as low-confidence payment signal
    if not event_type:
        addr = (msg.from_address or "").lower()
        domain = addr.split("@")[-1] if "@" in addr else ""
        known = any(domain == d or domain.endswith("." + d) or d in domain for d in KNOWN_MERCHANTS)
        if known and re.search(
            r"bill|plan|member|account|receipt|invoice|subscri|renew|trial|payment|charge",
            text,
            re.IGNORECASE,
        ):
            event_type, base_conf = "payment", 0.45
        else:
            return []

    amount, currency = _detect_amount(text)
    cycle = _detect_cycle(text)
    cancel_url = _detect_cancel_url(msg.snippet)

    # Boost confidence when amount present
    conf = base_conf
    if amount is not None:
        conf = min(1.0, conf + 0.1)
    if merchant in KNOWN_MERCHANTS.values() or any(
        msg.from_address.endswith(d) for d in KNOWN_MERCHANTS
    ):
        conf = min(1.0, conf + 0.05)

    return [
        ExtractedSignal(
            source_message_id=msg.id,
            merchant=merchant,
            normalized_name=normalized,
            event_type=event_type,
            event_date=msg.date,
            amount=amount,
            currency=currency,
            billing_cycle=cycle,
            snippet_evidence=(msg.snippet or msg.subject)[:280],
            confidence=conf,
            cancellation_url=cancel_url,
            from_address=msg.from_address,
            subject=msg.subject,
        )
    ]


def _detect_event(text: str) -> tuple[str | None, float]:
    for name, pattern, conf in EVENT_PATTERNS:
        if pattern.search(text):
            return name, conf
    return None, 0.0


def _detect_merchant(from_addr: str, from_name: str, subject: str) -> tuple[str | None, str]:
    addr = (from_addr or "").lower()
    domain = addr.split("@")[-1] if "@" in addr else ""
    # strip common mail subdomains
    domain_candidates = [domain]
    parts = domain.split(".")
    if len(parts) > 2:
        domain_candidates.append(".".join(parts[-2:]))
        # also try parent brand domain (e.g. mail.crunchyroll.com → crunchyroll.com)
        for i in range(len(parts) - 1):
            domain_candidates.append(".".join(parts[i:]))

    for d in domain_candidates:
        if d in KNOWN_MERCHANTS:
            name = KNOWN_MERCHANTS[d]
            return name, _slug(name)
        # fuzzy: any known key suffix-matches
        for known, name in KNOWN_MERCHANTS.items():
            if d.endswith(known) or known.endswith(d):
                return name, _slug(name)

    # Prefer registrable brand from domain before noisy display names
    # ("Chelsea with IFTTT" → prefer ifttt from domain)
    if domain and domain not in {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "yahoo.com",
    }:
        labels = [
            p
            for p in domain.split(".")
            if p
            not in {
                "email",
                "mail",
                "e",
                "t",
                "mp1",
                "news",
                "updates",
                "noreply",
                "no-reply",
                "notification",
                "notifications",
                "accounts",
                "billing",
                "support",
            }
        ]
        if labels:
            brand = (
                labels[-2]
                if len(labels) >= 2
                and labels[-1] in {"com", "io", "co", "net", "ai", "app", "so", "dev"}
                else labels[0]
            )
            # If display name is long/noisy, still use domain brand
            if (
                brand
                and brand not in {"www", "m"}
                and (not from_name or len(from_name) > 24 or " with " in from_name.lower())
            ):
                return brand.title(), _slug(brand)

    # name from display
    if from_name and len(from_name) > 1:
        cleaned = re.sub(
            r"\b(inc|llc|ltd|team|noreply|no-reply|notifications?)\b",
            "",
            from_name,
            flags=re.IGNORECASE,
        )
        cleaned = cleaned.strip(" -_|")
        if cleaned and len(cleaned) >= 2:
            return cleaned[:60], _slug(cleaned)

    if domain and domain not in {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "yahoo.com",
    }:
        base = domain.split(".")[0]
        if base not in {
            "email",
            "mail",
            "noreply",
            "no-reply",
            "notification",
            "notifications",
        }:
            return base.title(), _slug(base)

    # subject brand heuristic: first capitalized token
    m = re.match(r"^([A-Z][A-Za-z0-9]+)\b", subject or "")
    if m:
        return m.group(1), _slug(m.group(1))
    return None, ""


def _detect_amount(text: str) -> tuple[float | None, str | None]:
    m = AMOUNT_RE.search(text or "")
    if not m:
        return None, None
    cur = m.group("currency") or m.group("currency2") or ""
    raw = m.group("amount") or m.group("amount2") or ""
    raw = raw.replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        return None, None
    currency = _normalize_currency(cur)
    return amount, currency


def _normalize_currency(cur: str) -> str:
    cur = (cur or "").strip().upper()
    return {
        "$": "USD",
        "฿": "THB",
        "€": "EUR",
        "£": "GBP",
    }.get(cur, cur or "USD")


def _detect_cycle(text: str) -> str | None:
    m = CYCLE_RE.search(text or "")
    if not m:
        return None
    t = m.group(1).lower()
    if "year" in t or "annual" in t or "/yr" in t:
        return "annual"
    if "month" in t or "/mo" in t:
        return "monthly"
    if "week" in t:
        return "weekly"
    return "unknown"


def _detect_cancel_url(snippet: str) -> str | None:
    for url in URL_RE.findall(snippet or ""):
        low = url.lower()
        if any(k in low for k in ("cancel", "unsubscribe", "manage", "billing", "subscription")):
            return url.rstrip(").,;]")
    # List-Unsubscribe: <https://...>
    m = re.search(r"<(https?://[^>]+)>", snippet or "", re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "unknown"
