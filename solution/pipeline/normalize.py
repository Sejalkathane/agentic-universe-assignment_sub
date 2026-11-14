import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

IST = timezone(timedelta(hours=5, minutes=30))
_MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def normalise_header(h: str) -> str:
    return re.sub(r"[_\s]+", " ", h.lower().strip())


def normalise_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return "+91" + digits
    return None


def parse_date(raw: str) -> str | None:
    s = raw.strip()
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s):
            y, mo, d = map(int, m.groups())
        elif m := re.fullmatch(r"(\d{1,2})([/-])(\d{1,2})\2(\d{4})", s):
            d, mo, y = int(m[1]), int(m[3]), int(m[4])
        elif m := re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", s):
            mon = _MONTHS.get(m[2].lower())
            if mon is None:
                return None
            d, mo, y = int(m[1]), mon, int(m[3])
        else:
            return None
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


_DEC = re.compile(r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?|\.\d+)", re.I)


def parse_decimal(raw: str) -> str | None:
    m = _DEC.fullmatch(raw.strip())
    if not m:
        return None
    val = Decimal(m[1].replace(",", ""))
    return str(val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_timestamp(raw: str) -> datetime:
    """Returns aware UTC datetime. Naive means IST. Raises ValueError if bad."""
    s = raw.strip()
    if not s:
        raise ValueError("empty timestamp")
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc)


def parse_value(ftype: str, raw: str, enum_values=()):
    """raw is non-empty and trimmed. Returns (ok, value)."""
    if ftype == "string":
        return True, raw
    if ftype == "phone":
        v = normalise_phone(raw)
    elif ftype == "date":
        v = parse_date(raw)
    elif ftype == "decimal":
        v = parse_decimal(raw)
    elif ftype == "enum":
        allowed = {e.lower() for e in enum_values}
        v = raw.lower() if raw.lower() in allowed else None
    else:
        raise ValueError(f"unknown field type {ftype}")
    return v is not None, v