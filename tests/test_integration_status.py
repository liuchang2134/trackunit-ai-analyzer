import json
from app import integration_status as integration


def test_missing_or_corrupt_report_does_not_claim_connectivity(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    monkeypatch.setattr(integration, "STATUS_PATH", path)
    assert integration.integration_status()["status"] == "not_verified"
    path.write_text('{broken', encoding="utf-8")
    assert integration.integration_status()["status"] == "not_verified"


def test_public_response_drops_unexpected_private_fields(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    monkeypatch.setattr(integration, "STATUS_PATH", path)
    path.write_text(json.dumps({"checked_at":"2020-01-02T00:00:00Z", "window_start":"2020-01-01T00:00:00Z",
        "window_end":"2020-01-02T00:00:00Z", "secret":"do-not-return", "asset_id":"private",
        "capabilities":[{"name":"idle_hours","status":"empty","record_count":0,"http_status":200},
            {"name":"fault_events","status":"unauthorized","http_status":401,"response_body":"private"}]}),encoding="utf-8")
    result = integration.integration_status()
    assert result["older_than_24h"] is True and result["is_live_check"] is False
    assert result["capabilities"][0]["status"] == "empty"
    assert result["capabilities"][1]["status"] == "unauthorized"
    assert "private" not in json.dumps(result) and "do-not-return" not in json.dumps(result)
