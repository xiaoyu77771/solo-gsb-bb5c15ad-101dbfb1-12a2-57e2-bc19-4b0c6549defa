"""Tests for the /expand endpoint and the DST classification logic."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

NY = "America/New_York"
# America/New_York 2024 transitions:
#   spring forward 2024-03-10 02:00 -> 03:00 (02:30 does not exist)
#   fall back     2024-11-03 02:00 -> 01:00 (01:30 occurs twice)


def post(payload: dict):
    return client.post("/expand", json=payload)


def base_payload(**overrides) -> dict:
    payload = {
        "timezone": NY,
        "start_date": "2024-03-10",
        "end_date": "2024-03-10",
        "weekdays": [6],  # Sunday
        "local_time": "02:30",
        "gap_strategy": "skip",
        "fold_strategy": "first",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------- normal ---


def test_normal_day_single_instance():
    resp = post(
        base_payload(
            start_date="2024-01-01",
            end_date="2024-01-07",
            weekdays=[0],  # Monday
            local_time="09:00",
        )
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["instances"] == [
        {
            "local": "2024-01-01T09:00:00",
            "offset": "-05:00",
            "utc": "2024-01-01T14:00:00Z",
            "reason": "normal",
        }
    ]


def test_weekday_filter_and_utc_sorting():
    resp = post(
        base_payload(
            start_date="2024-01-01",
            end_date="2024-01-14",
            weekdays=[0, 2, 4],  # Mon/Wed/Fri
            local_time="09:00",
        )
    )
    assert resp.status_code == 200
    instances = resp.json()["instances"]
    assert [i["local"] for i in instances] == [
        "2024-01-01T09:00:00",
        "2024-01-03T09:00:00",
        "2024-01-05T09:00:00",
        "2024-01-08T09:00:00",
        "2024-01-10T09:00:00",
        "2024-01-12T09:00:00",
    ]
    utcs = [i["utc"] for i in instances]
    assert utcs == sorted(utcs)
    assert all(i["reason"] == "normal" for i in instances)


# -------------------------------------------------------------------- gap ---


def test_gap_skip_produces_no_instance():
    resp = post(base_payload(gap_strategy="skip"))
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert resp.json()["instances"] == []


def test_gap_shift_forward_moves_by_gap_delta():
    resp = post(base_payload(gap_strategy="shift_forward"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    # 02:30 never happened; the 1-hour gap delta moves it to 03:30 EDT.
    assert body["instances"][0] == {
        "local": "2024-03-10T03:30:00",
        "offset": "-04:00",
        "utc": "2024-03-10T07:30:00Z",
        "reason": "gap_shift_forward",
    }


def test_gap_only_affects_transition_day():
    resp = post(
        base_payload(
            start_date="2024-03-08",
            end_date="2024-03-12",
            weekdays=[0, 1, 2, 3, 4, 5, 6],
            gap_strategy="shift_forward",
        )
    )
    assert resp.status_code == 200
    instances = resp.json()["instances"]
    assert [i["reason"] for i in instances] == [
        "normal",
        "normal",
        "gap_shift_forward",
        "normal",
        "normal",
    ]
    assert instances[2]["local"] == "2024-03-10T03:30:00"


# ------------------------------------------------------------------- fold ---


def fold_payload(strategy: str) -> dict:
    return base_payload(
        start_date="2024-11-03",
        end_date="2024-11-03",
        local_time="01:30",
        fold_strategy=strategy,
    )


def test_fold_first_picks_earlier_utc():
    resp = post(fold_payload("first"))
    assert resp.status_code == 200
    assert resp.json()["instances"] == [
        {
            "local": "2024-11-03T01:30:00",
            "offset": "-04:00",
            "utc": "2024-11-03T05:30:00Z",
            "reason": "fold_first",
        }
    ]


def test_fold_second_picks_later_utc():
    resp = post(fold_payload("second"))
    assert resp.status_code == 200
    assert resp.json()["instances"] == [
        {
            "local": "2024-11-03T01:30:00",
            "offset": "-05:00",
            "utc": "2024-11-03T06:30:00Z",
            "reason": "fold_second",
        }
    ]


def test_fold_both_emits_two_instances_sorted_by_utc():
    resp = post(fold_payload("both"))
    assert resp.status_code == 200
    instances = resp.json()["instances"]
    assert len(instances) == 2
    assert [i["reason"] for i in instances] == ["fold_first", "fold_second"]
    assert [i["utc"] for i in instances] == [
        "2024-11-03T05:30:00Z",
        "2024-11-03T06:30:00Z",
    ]
    assert [i["offset"] for i in instances] == ["-04:00", "-05:00"]


def test_instances_are_deduplicated_by_utc():
    resp = post(fold_payload("both"))
    utcs = [i["utc"] for i in resp.json()["instances"]]
    assert len(utcs) == len(set(utcs))


# ------------------------------------------------------------- validation ---


def test_invalid_timezone_returns_422():
    resp = post(base_payload(timezone="Not/AZone"))
    assert resp.status_code == 422


def test_reversed_date_range_returns_422():
    resp = post(base_payload(start_date="2024-03-10", end_date="2024-03-01"))
    assert resp.status_code == 422


def test_range_over_366_days_returns_422():
    resp = post(base_payload(start_date="2024-01-01", end_date="2025-01-02"))
    assert resp.status_code == 422


def test_range_of_exactly_366_days_is_allowed():
    resp = post(
        base_payload(
            start_date="2024-01-01",
            end_date="2025-01-01",  # 366 days across leap year 2024
            weekdays=[0],
            local_time="09:00",
        )
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 53  # Mondays in that span


@pytest.mark.parametrize("weekdays", [[7], [-1], []])
def test_invalid_weekdays_return_422(weekdays):
    resp = post(base_payload(weekdays=weekdays))
    assert resp.status_code == 422


def test_invalid_strategy_returns_422():
    resp = post(base_payload(gap_strategy="explode"))
    assert resp.status_code == 422


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
