from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse, urlunparse

DUTCH_MONTHS = {
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}

DATE_PATTERN = re.compile(
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>januari|februari|maart|april|mei|juni|juli|augustus|"
    r"september|oktober|november|december)\s+"
    r"(?P<year>20\d{2})",
    re.IGNORECASE,
)



def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug or "cao"



def clean_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()



def normalize_html_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))



def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()



def parse_dutch_date(value: str) -> date | None:
    match = DATE_PATTERN.search(value)
    if not match:
        return None
    return date(
        int(match.group("year")),
        DUTCH_MONTHS[match.group("month").lower()],
        int(match.group("day")),
    )



def parse_all_dutch_dates(value: str) -> list[date]:
    result: list[date] = []
    for match in DATE_PATTERN.finditer(value):
        result.append(
            date(
                int(match.group("year")),
                DUTCH_MONTHS[match.group("month").lower()],
                int(match.group("day")),
            )
        )
    return result



def parse_term(value: str) -> tuple[date | None, date | None]:
    dates = parse_all_dutch_dates(value)
    if not dates:
        return None, None
    if len(dates) == 1:
        return dates[0], None
    return dates[0], dates[1]



def parse_decimal(value: str) -> Decimal | None:
    cleaned = value.strip().replace("€", "").replace(" ", "")
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")

    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
