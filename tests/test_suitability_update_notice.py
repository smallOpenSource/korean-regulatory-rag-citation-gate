"""Stage 3 T221 — yearly suitability confirmation update notice."""

from __future__ import annotations

from datetime import date

import pytest

from apps.api.harness.services.compliance.suitability_update_notice import (
    GRACE_DAYS,
    NOTICE_INTERVAL_DAYS,
    build_notice_payload,
    classify,
    days_until_notice_due,
    is_notice_due,
    is_notice_due_soon,
    partition_customers,
)


def test_interval_is_365_days():
    assert NOTICE_INTERVAL_DAYS == 365


def test_grace_window_is_14_days():
    assert GRACE_DAYS == 14


def test_days_until_notice_due_in_future():
    last = date(2026, 5, 1)
    today = date(2026, 5, 15)
    assert days_until_notice_due(last, today) == 365 - 14


def test_days_until_notice_due_overdue():
    last = date(2025, 1, 1)
    today = date(2026, 5, 15)
    assert days_until_notice_due(last, today) < 0


def test_is_notice_due_never_issued():
    assert is_notice_due(None, date(2026, 5, 18)) is True


def test_is_notice_due_overdue():
    assert is_notice_due(date(2025, 1, 1), date(2026, 5, 18)) is True


def test_is_notice_due_not_yet():
    assert is_notice_due(date(2026, 5, 1), date(2026, 5, 18)) is False


def test_is_notice_due_soon_within_grace():
    today = date(2026, 5, 18)
    # last issued such that ~7 days remaining
    last = today - (date(2027, 5, 18) - date(2026, 5, 18)) + (date(2026, 5, 25) - today)
    # Reset more simply: pick last such that next_due = today+7
    last2 = today + (date(2026, 5, 25) - today) - (date(2027, 5, 18) - date(2026, 5, 18))
    # Cleaner: target next_due = today + 7 → last = today + 7 - 365
    last_clean = today + (date(2026, 5, 25) - today)
    from datetime import timedelta
    last_clean = today + timedelta(days=7) - timedelta(days=NOTICE_INTERVAL_DAYS)
    assert is_notice_due_soon(last_clean, today) is True


def test_is_notice_due_soon_excludes_overdue():
    today = date(2026, 5, 18)
    last = date(2024, 1, 1)  # very old → overdue
    assert is_notice_due_soon(last, today) is False


def test_is_notice_due_soon_none_returns_false():
    assert is_notice_due_soon(None, date(2026, 5, 18)) is False


def test_classify_never_issued():
    assert classify(None, date(2026, 5, 18)) == "never_issued"


def test_classify_overdue():
    assert classify(date(2024, 1, 1), date(2026, 5, 18)) == "overdue"


def test_classify_due_today():
    today = date(2026, 5, 18)
    from datetime import timedelta
    last = today - timedelta(days=NOTICE_INTERVAL_DAYS)
    assert classify(last, today) == "due_today"


def test_classify_due_soon():
    today = date(2026, 5, 18)
    from datetime import timedelta
    last = today + timedelta(days=7) - timedelta(days=NOTICE_INTERVAL_DAYS)
    assert classify(last, today) == "due_soon"


def test_classify_current():
    today = date(2026, 5, 18)
    last = date(2026, 5, 1)  # only 17 days old → current
    assert classify(last, today) == "current"


def test_build_notice_payload_contains_required_fields():
    payload = build_notice_payload(
        customer_id="cust-1",
        employee_id="emp-1",
        today=date(2026, 5, 18),
        last_notice_at=date(2025, 5, 18),
    )
    assert payload["customer_id"] == "cust-1"
    assert payload["employee_id"] == "emp-1"
    assert payload["issued_on"] == "2026-05-18"
    assert payload["previous_notice_at"] == "2025-05-18"
    assert payload["next_due_on"] == "2027-05-18"
    assert payload["audit_action_code"] == "SUITABILITY_UPDATE_NOTICE_SHOWN"


def test_build_notice_payload_new_customer():
    payload = build_notice_payload(
        customer_id="cust-1",
        employee_id="emp-1",
        today=date(2026, 5, 18),
        last_notice_at=None,
    )
    assert payload["previous_notice_at"] is None
    assert payload["trigger_status"] == "never_issued"


def test_build_notice_payload_rejects_missing_ids():
    with pytest.raises(ValueError):
        build_notice_payload(
            customer_id="",
            employee_id="emp-1",
            today=date(2026, 5, 18),
            last_notice_at=None,
        )


def test_partition_customers_buckets_all_classes():
    today = date(2026, 5, 18)
    from datetime import timedelta
    customers = [
        {"customer_id": "c-new", "last_notice_at": None},
        {"customer_id": "c-overdue", "last_notice_at": date(2024, 1, 1)},
        {"customer_id": "c-current", "last_notice_at": date(2026, 5, 1)},
        {"customer_id": "c-soon", "last_notice_at": today + timedelta(days=7) - timedelta(days=NOTICE_INTERVAL_DAYS)},
        {"customer_id": "c-today", "last_notice_at": today - timedelta(days=NOTICE_INTERVAL_DAYS)},
    ]
    buckets = partition_customers(customers, today)
    assert [r["customer_id"] for r in buckets["never_issued"]] == ["c-new"]
    assert [r["customer_id"] for r in buckets["overdue"]] == ["c-overdue"]
    assert [r["customer_id"] for r in buckets["current"]] == ["c-current"]
    assert [r["customer_id"] for r in buckets["due_soon"]] == ["c-soon"]
    assert [r["customer_id"] for r in buckets["due_today"]] == ["c-today"]


def test_partition_customers_rejects_bad_date_type():
    with pytest.raises(TypeError):
        partition_customers(
            [{"customer_id": "c", "last_notice_at": "not-a-date"}],
            date(2026, 5, 18),
        )


def test_deterministic_classification_across_repeated_calls():
    last = date(2025, 5, 18)
    today = date(2026, 5, 18)
    runs = {classify(last, today) for _ in range(50)}
    assert len(runs) == 1
