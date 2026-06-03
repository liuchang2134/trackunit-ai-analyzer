from app.live_data_service import collect_live_data
from app.trackunit_client import TrackunitError


class FailingClient:
    def get_machine_list(self):
        raise TrackunitError("Trackunit API endpoint is not configured")


class FakeClient:
    def get_machine_list(self):
        return {
            "equipment": [
                {
                    "assetId": "M-LIVE-1",
                    "SerialNumber": "LIVE123",
                    "EquipmentHeader": {"Model": "XE490U"},
                    "lastSeenAt": "2026-06-02T12:00:00Z",
                }
            ]
        }

    def get_telemetry(self, machine_query=None, start=None, end=None):
        return [
            {
                "assetId": "M-LIVE-1",
                "CumulativeOperatingHours": {"Hour": 100},
                "FuelRemaining": {"Percent": 8},
                "EngineStatus": {"Running": False},
                "recordedAt": "2026-06-02T12:00:00Z",
            }
        ]


def test_collect_live_data_falls_back_to_cache(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "mock")
    monkeypatch.setenv("TRACKUNIT_CACHE_FIRST", "false")
    result = collect_live_data(
        {"intent": "offline_machines", "filters": {"offline_hours": 72}},
        client=FailingClient(),
    )

    assert result["fallback_used"] is True
    assert result["source"] == "mock"
    assert result["data_summary"]["machines_scanned"] == 5
    assert "endpoint is not configured" in result["api_error"]


def test_collect_live_data_uses_trackunit_api(monkeypatch):
    monkeypatch.setenv("TRACKUNIT_CACHE_FIRST", "false")
    result = collect_live_data(
        {"intent": "low_fuel", "filters": {"fuel_threshold_percent": 10}},
        client=FakeClient(),
    )

    assert result["source"] == "trackunit_api"
    assert result["fallback_used"] is False
    assert result["machines"][0]["serial_number"] == "LIVE123"
    assert result["machines"][0]["fuel_remaining_percent"] == 8
    assert result["api_calls"] == ["machines", "telemetry"]


def test_collect_live_data_uses_fresh_cache_before_api(monkeypatch):
    class ShouldNotCallClient:
        def get_machine_list(self):
            raise AssertionError("API should not be called when cache is fresh")

    monkeypatch.setenv("DATA_SOURCE", "mock")
    monkeypatch.setenv("TRACKUNIT_CACHE_FIRST", "true")
    monkeypatch.setattr("app.live_data_service.cache_status", lambda: {
        "exists": True,
        "fresh": True,
        "updated_at": "2026-06-02T12:00:00+00:00",
        "age_seconds": 30,
        "ttl_seconds": 300,
    })

    result = collect_live_data(
        {"intent": "low_fuel", "filters": {"fuel_threshold_percent": 10}},
        client=ShouldNotCallClient(),
    )

    assert result["source"] == "mock"
    assert result["fallback_used"] is False
    assert result["data_summary"]["cache_fresh"] is True
