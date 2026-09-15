from app import data_store
from app.models import Machine


def test_data_store_falls_back_to_mock(monkeypatch, tmp_path):
    monkeypatch.setattr(data_store, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(data_store, "MACHINES_CACHE", tmp_path / "machines_cache.json")
    monkeypatch.setattr(data_store, "TELEMETRY_CACHE", tmp_path / "telemetry_cache.json")
    monkeypatch.setattr(data_store, "FAULTS_CACHE", tmp_path / "faults_cache.json")
    monkeypatch.setenv("DATA_SOURCE", "mock")

    machines = data_store.load_machines()

    assert len(machines) == 5
    assert machines[0].machine_id == "M-1001"


def test_data_store_reads_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(data_store, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(data_store, "MACHINES_CACHE", tmp_path / "machines_cache.json")
    monkeypatch.setattr(data_store, "TELEMETRY_CACHE", tmp_path / "telemetry_cache.json")
    monkeypatch.setattr(data_store, "FAULTS_CACHE", tmp_path / "faults_cache.json")
    monkeypatch.setenv("DATA_SOURCE", "trackunit_cache")

    data_store.save_machines([
        Machine(
            machine_id="CACHE-1",
            serial_number="SERIAL-1",
            model="XC958",
            machine_type="wheel loader",
            customer="Cache Customer",
            location="Houston, TX",
            last_seen_at="2026-06-02T14:00:00Z",
        )
    ])

    machines = data_store.load_machines()

    assert len(machines) == 1
    assert machines[0].machine_id == "CACHE-1"



def test_partial_real_cache_never_loads_demo_faults(monkeypatch, tmp_path):
    monkeypatch.setattr(data_store, "MACHINES_CACHE", tmp_path / "machines.json")
    monkeypatch.setattr(data_store, "TELEMETRY_CACHE", tmp_path / "telemetry.json")
    monkeypatch.setattr(data_store, "FAULTS_CACHE", tmp_path / "faults.json")
    monkeypatch.setenv("DATA_SOURCE", "trackunit_cache")
    (tmp_path / "machines.json").write_text("[]")
    assert data_store.get_data_source() == "trackunit_cache"
    assert data_store.load_faults() == []
    assert data_store.load_telemetry() == []
