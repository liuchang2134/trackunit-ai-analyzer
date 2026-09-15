import pytest
from pydantic import ValidationError
from app import local_datasets as store


@pytest.fixture
def payload(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATASETS", tmp_path / "datasets")
    return {"name": "Excavator shift", "source_document": "synthetic fixture v1",
        "provenance": "synthetic", "replay_at": "2026-01-01T12:00:00Z",
        "machine": {"machine_id": "SIM-1", "model": "SIM-EX", "serial_number": "DEMO-1",
            "machine_type": "excavator", "customer": "demo", "location": "synthetic", "last_seen_at": "2026-01-01T12:00:00Z"},
        "telemetry": [{"machine_id": "SIM-1", "recorded_at": "2026-01-01T12:00:00Z", "operating_hours": 102, "idle_hours": 50.5},
                      {"machine_id": "SIM-1", "recorded_at": "2026-01-01T10:00:00Z", "operating_hours": 100, "idle_hours": 50}]}


def test_isolated_sorted_idempotent_import(payload):
    ds = store.LocalDataset.model_validate(payload)
    saved = store.save_dataset(ds)
    assert store.save_dataset(ds) == saved
    loaded = store.load_dataset(saved["dataset_id"])
    assert loaded.telemetry[0].operating_hours == 100
    assert len(store.list_datasets()) == 1
    assert saved["provenance"] == "synthetic"


@pytest.mark.parametrize("bad", ["../../.env", "0" * 63, "A" * 64])
def test_dataset_path_cannot_escape(payload, bad):
    with pytest.raises(ValueError):
        store.load_dataset(bad)


def test_future_truth_and_other_machine_rejected(payload):
    payload["replay_at"] = "2026-01-01T11:00:00Z"
    with pytest.raises(ValidationError):
        store.LocalDataset.model_validate(payload)
    payload["replay_at"] = "2026-01-01T12:00:00Z"
    payload["telemetry"][0]["machine_id"] = "OTHER"
    with pytest.raises(ValidationError):
        store.LocalDataset.model_validate(payload)


def test_csv_units_missing_values_and_bad_columns(payload):
    base = {k:v for k,v in payload.items() if k != "telemetry"}
    request = store.CsvDatasetRequest(**base, csv_text="recorded_at,operating_hours,idle_hours,fuel_remaining_percent\n2026-01-01T10:00:00Z,100,50,\n2026-01-01T12:00:00Z,102,50.5,40\n")
    ds = store.parse_csv(request)
    assert ds.telemetry[0].fuel_remaining_percent is None
    assert ds.telemetry[1].fuel_remaining_percent == 40
    for text in ["recorded_at,unknown\n2026-01-01T10:00:00Z,2", "recorded_at,operating_hours\n2026-01-01T10:00:00Z,NaN", "recorded_at,operating_hours\n2026-01-01T10:00:00Z,1,2"]:
        with pytest.raises(ValueError):
            store.parse_csv(request.model_copy(update={"csv_text": text}))


def test_real_data_cannot_use_synthetic_clock(payload):
    payload["provenance"] = "user_supplied"
    with pytest.raises(ValidationError):
        store.LocalDataset.model_validate(payload)


def test_investigation_reads_import_instead_of_fleet(payload, monkeypatch):
    from app import local_assistant as agent
    saved = store.save_dataset(store.LocalDataset.model_validate(payload))
    def forbidden(*args):
        raise AssertionError("Fleet data must not be read for imported dataset")
    monkeypatch.setattr(agent, "find_machine", forbidden)
    answers = iter([agent.Decision(action="snapshot"), agent.Decision(action="trends"), agent.Decision(action="finish",summary="Synthetic window analyzed", evidence_ids=["tool:2:trends"])])
    monkeypatch.setattr(agent,"model_step",lambda *args:next(answers))
    result=agent.investigate(agent.InvestigationRequest(machine_id="SIM-1",dataset_id=saved["dataset_id"],question="Idle trend"))
    trend=result["evidence"]["tool:2:trends"]
    assert trend["idle_share"] == .25
    assert trend["latest_age_hours"] == 0
    assert result["source"] == "imported_synthetic"
