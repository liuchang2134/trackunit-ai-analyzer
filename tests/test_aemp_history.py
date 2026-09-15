import pytest
from app.aemp_history import normalize_hour_series


def test_separate_times_stay_separate_and_zero_is_retained():
    rows = normalize_hour_series("A", {"cumulativeOperatingHours": [
        {"Hour": 0, "datetime": "2026-09-12T12:00:00Z"}]},
        {"cumulativeIdleHours": [{"Hour": 0, "datetime": "2026-09-12T12:01:00Z"}]})
    assert rows[0].operating_hours == 0 and rows[0].idle_hours is None
    assert rows[1].operating_hours is None and rows[1].idle_hours == 0


def test_missing_idle_is_not_zero():
    rows = normalize_hour_series("A", {"cumulativeOperatingHours": [
        {"Hour": 19.1, "datetime": "2026-09-12T12:00:00Z"}]}, {"cumulativeIdleHours": []})
    assert rows[0].idle_hours is None


def test_conflicting_counter_is_rejected():
    with pytest.raises(ValueError, match="Conflicting"):
        normalize_hour_series("A", {"cumulativeOperatingHours": [
            {"Hour": 1, "datetime": "2026-09-12T12:00:00Z"},
            {"Hour": 2, "datetime": "2026-09-12T12:00:00Z"}]}, {"cumulativeIdleHours": []})
