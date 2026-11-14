from datetime import datetime, timezone
from pipeline.normalize import (normalise_header, normalise_phone, parse_date,
                                parse_decimal, parse_timestamp)
from pipeline.reports import Call, effective_code, bucket


def test_phone():
    assert normalise_phone("91-77187-50036") == "+917718750036"
    assert normalise_phone("07718750036") == "+917718750036"
    assert normalise_phone("+91 77187 50036") == "+917718750036"
    assert normalise_phone("5718750036") is None
    assert normalise_phone("77187500") is None
    assert normalise_phone("") is None


def test_dates():
    assert parse_date("2026-12-01") == "2026-12-01"
    assert parse_date("01/12/2026") == "2026-12-01"
    assert parse_date("01-12-2026") == "2026-12-01"
    assert parse_date("01-DEC-2026") == "2026-12-01"
    assert parse_date("31/02/2026") is None


def test_decimal():
    assert parse_decimal("₹1,25,000.456") == "125000.46"
    assert parse_decimal("rs. 500") == "500.00"
    assert parse_decimal("INR1,000") == "1000.00"
    assert parse_decimal("-5") is None


def test_timestamps():
    utc = parse_timestamp("2026-10-03T04:31:00Z")
    assert parse_timestamp("2026-10-03 10:01:00") == utc
    assert parse_timestamp("2026-10-03T10:01:00+05:30") == utc


def test_header():
    assert normalise_header("  Customer__Name ") == "customer name"


def mk(**kw):
    return Call(1, datetime(2026, 1, 1, tzinfo=timezone.utc), **kw)


def test_effective_disposition():
    assert effective_code(mk()) is None
    assert effective_code(mk(sets=["a", "b"])) == "b"
    assert effective_code(mk(sets=["a"], overrides=["x", "y"])) == "y"


def test_bucket():
    term = lambda c: c == "renewed"
    assert bucket([], term) == "yet_to_reach_out"
    assert bucket([mk(failed=True), mk(sets=["renewed"])], term) == "completed"
    assert bucket([mk(failed=True), mk(failed=True)], term) == "in_progress_telephony_failed"
    assert bucket([mk(failed=True), mk()], term) == "in_progress_dialed"
    assert bucket([mk(sets=["renewed"], overrides=["callback"])], term) == "in_progress_dialed"