from app import local_assistant as agent, local_datasets, parts_catalog
from app.check_options import build_check_options
from scripts.prepare_parts_demo import build_demo, ROOT


def test_demo_replay_matches_only_synthetic_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(local_datasets, "DATASETS", tmp_path / "datasets")
    monkeypatch.setattr(parts_catalog, "CATALOG_PATH", tmp_path / "parts.json")
    demo = build_demo()
    saved = local_datasets.save_dataset(demo)
    catalog = parts_catalog.CatalogImport.model_validate_json((ROOT / "docs/examples/demo-parts-catalog.json").read_text(encoding="utf-8"))
    parts_catalog.import_catalog(catalog)
    part=catalog.parts[0]
    check_id=build_check_options({'catalog:'+part.part_number:part.model_dump()})[0]['check_id']
    actions = iter([agent.Decision(action="snapshot"), agent.Decision(action="faults"),
        agent.Decision(action="parts"), agent.Decision(action="finish", summary="演示候选，需现场检查", evidence_ids=["tool:3:parts"],next_check_ids=[check_id])])
    monkeypatch.setattr(agent, "model_step", lambda *args: next(actions))
    result = agent.investigate(agent.InvestigationRequest(machine_id=demo.machine.machine_id,
        dataset_id=saved["dataset_id"], question="检查告警并查找备件"))
    assert result["source"] == "imported_synthetic"
    assert result["parts_candidates"][0]["part_number"] == "DEMO-BOOST-SENSOR"
    assert result["parts_candidates"][0]["serial_verified"] is False
    assert result["parts_candidates"][0]["match_reason"] == "fault_code"
    assert result['check_recommendations'][0]['provenance']=='demo'
    assert not parts_catalog.search_parts("XE135U", fault_codes=["ENG-BOOST-102-3"], include_demo=False)
    assert all(f.occurred_at <= demo.replay_at.isoformat() for f in demo.faults)
