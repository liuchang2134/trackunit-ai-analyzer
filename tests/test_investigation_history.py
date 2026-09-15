import pytest
from app import investigation_history as history


def test_record_is_immutable_and_preserves_operator_input(tmp_path,monkeypatch):
    monkeypatch.setattr(history,"HISTORY_DIR",tmp_path)
    report={"status":"completed","machine_id":"A","source":"mock","generated_at":"2026-01-01T00:00:00Z","summary":"检查线束"}
    request={"machine_id":"A","question":"检查故障","observations":"接头无松脱","secret":"never-save"}
    saved=history.save_investigation(report,request)
    assert saved==history.read_investigation(saved["record_id"])
    assert "secret" not in saved["request"]
    assert history.save_investigation(report,request)["record_id"]==saved["record_id"]
    request["observations"]="发现磨损"
    assert history.save_investigation(report,request)["record_id"]!=saved["record_id"]
    assert history.list_investigations()["total"]==2
    assert history.read_investigation(saved["record_id"])["request"]["observations"]=="接头无松脱"
    (tmp_path/(saved["record_id"]+".json")).write_text('{}',encoding="utf-8")
    with pytest.raises(ValueError,match="integrity"):
        history.read_investigation(saved["record_id"])
    assert history.list_investigations()["unreadable"]==1


def test_path_escape_and_incomplete_report_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(history,"HISTORY_DIR",tmp_path)
    with pytest.raises(ValueError):history.read_investigation('../secrets')
    with pytest.raises(ValueError):history.save_investigation({"status":"failed"},{"machine_id":"A"})


def test_history_filters_device_version_and_source_before_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(history, 'HISTORY_DIR', tmp_path)
    for n, (machine, dataset, source) in enumerate([
        ('A', 'version-1', 'imported_synthetic'), ('A', 'version-2', 'imported_synthetic'),
        ('A', None, 'mock'), ('B', None, 'mock'), ('A', None, 'trackunit_cache')
    ]):
        history.save_investigation(
            {'status':'completed', 'machine_id':machine, 'source':source,
             'generated_at':f'2026-01-0{n+1}T00:00:00Z', 'summary':'check'},
            {'machine_id':machine, 'dataset_id':dataset, 'question':'check'})
    assert history.list_investigations()['total'] == 5
    assert history.list_investigations(machine_id='A')['total'] == 4
    version = history.list_investigations(limit=1, machine_id='A', dataset_id='version-1')
    assert version['total'] == 1
    assert version['records'][0]['dataset_id'] == 'version-1'
    fleet = history.list_investigations(machine_id='A', dataset_id='', source='mock')
    assert fleet['total'] == 1
    assert fleet['records'][0]['source'] == 'mock'
    assert history.list_investigations(machine_id='missing')['total'] == 0
