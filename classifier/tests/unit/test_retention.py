"""Unit tests for the archive-only retention classification + keep-until (docs/retention-policy.md)."""

from __future__ import annotations

import datetime as dt

from app.retention import RETENTION_YEARS, classify, keep_until

F2N = {10: "policy_number", 11: "claim_number", 12: "client"}
T2N = {1: "filed", 2: "needs-review", 3: "kyc", 4: "regulatory", 5: "internal"}


def _doc(custom=None, tags=None):
    return {"id": 1, "custom_fields": custom or [], "tags": tags or [], "created": "2020-06-15"}


def test_claim_field_wins():
    d = _doc(custom=[{"field": 11, "value": "CLM-1"}], tags=[3])  # claim# + kyc tag
    assert classify(d, F2N, T2N) == "claim"  # explicit field beats the tag


def test_policy_field():
    assert classify(_doc(custom=[{"field": 10, "value": "POL-9"}]), F2N, T2N) == "policy"


def test_empty_field_value_ignored():
    # a present-but-empty policy_number must NOT classify as policy
    assert classify(_doc(custom=[{"field": 10, "value": ""}]), F2N, T2N) == "default"


def test_class_tag():
    assert classify(_doc(tags=[4]), F2N, T2N) == "regulatory"
    assert classify(_doc(tags=[5]), F2N, T2N) == "internal"


def test_default_when_unmapped():
    assert classify(_doc(tags=[1]), F2N, T2N) == "default"  # only the `filed` tag → default
    assert RETENTION_YEARS["default"] == 10


def test_keep_until_adds_window():
    assert keep_until("2020-06-15", "policy") == dt.date(2030, 6, 15)  # 10y
    assert keep_until("2020-06-15", "kyc") == dt.date(2025, 6, 15)  # 5y
    assert keep_until("2020-06-15", "internal") == dt.date(2023, 6, 15)  # 3y


def test_keep_until_leap_day():
    # 29 Feb + 10y (2030 not leap) → clamp to 28 Feb, no ValueError
    assert keep_until("2020-02-29", "policy") == dt.date(2030, 2, 28)


def test_keep_until_accepts_datetime_iso():
    assert keep_until("2020-06-15T09:30:00Z", "financial") == dt.date(2030, 6, 15)
