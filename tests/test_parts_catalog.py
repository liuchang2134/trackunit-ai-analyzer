import pytest
from pydantic import ValidationError
from app import parts_catalog as catalog


@pytest.fixture
def payload(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "CATALOG_PATH", tmp_path / "parts.json")
    return {"parts": [{"part_number": "DEMO-SENSOR-1", "name": "演示传感器",
        "component": "pressure sensor", "models": ["DEMO-EXC"],
        "fault_codes": ["DEMO-PRESSURE"], "checks": ["核实接头状态与测量结果"],
        "source_document": "Synthetic catalog", "source_page": "1", "revision": "demo-v1",
        "provenance": "demo"}]}


def test_demo_not_returned_for_real_data(payload):
    catalog.import_catalog(catalog.CatalogImport.model_validate(payload))
    assert catalog.search_parts("DEMO-EXC", fault_codes=["DEMO-PRESSURE"]) == []
    found = catalog.search_parts("DEMO-EXC", fault_codes=["DEMO-PRESSURE"], include_demo=True)
    assert found[0]["status"] == "candidate_requires_inspection"
    assert not found[0]["serial_verified"]
    assert found[0]["source_id"] == "catalog:DEMO-SENSOR-1"


def test_model_serial_and_fault_constraints(payload):
    payload["parts"][0].update(applicability="serial_list", serial_numbers=["SN001"])
    catalog.import_catalog(catalog.CatalogImport.model_validate(payload))
    assert catalog.search_parts("OTHER", "SN001", ["DEMO-PRESSURE"], include_demo=True) == []
    assert catalog.search_parts("DEMO-EXC", "SN002", ["DEMO-PRESSURE"], include_demo=True) == []
    assert catalog.search_parts("DEMO-EXC", "SN001", ["UNKNOWN"], include_demo=True) == []
    assert catalog.search_parts("DEMO-EXC", "SN001", ["DEMO-PRESSURE"], include_demo=True)[0]["serial_verified"]


def test_duplicate_and_conflict_leave_existing_file_intact(payload):
    parsed = catalog.CatalogImport.model_validate(payload)
    assert catalog.import_catalog(parsed)["added"] == 1
    assert catalog.import_catalog(parsed)["added"] == 0
    before = catalog.CATALOG_PATH.read_bytes()
    payload["parts"][0]["name"] = "changed"
    with pytest.raises(ValueError, match="Conflicting"):
        catalog.import_catalog(catalog.CatalogImport.model_validate(payload))
    assert catalog.CATALOG_PATH.read_bytes() == before
    payload["parts"] *= 2
    with pytest.raises(ValidationError):
        catalog.CatalogImport.model_validate(payload)


def test_missing_citation_or_serial_scope_rejected(payload):
    del payload["parts"][0]["source_page"]
    with pytest.raises(ValidationError):
        catalog.CatalogImport.model_validate(payload)
    payload["parts"][0]["source_page"] = "1"
    payload["parts"][0]["applicability"] = "serial_list"
    with pytest.raises(ValidationError):
        catalog.CatalogImport.model_validate(payload)


def test_search_explains_each_filter_without_returning_rejected_parts(payload):
    report={}
    assert not catalog.search_parts('DEMO-EXC',diagnostics=report)
    assert report['reason_code']=='catalog_empty'
    payload['parts'][0].update(applicability='serial_list',serial_numbers=['SN001'])
    catalog.import_catalog(catalog.CatalogImport.model_validate(payload))
    cases=[('DEMO-EXC','SN001',['DEMO-PRESSURE'],False,'no_eligible_catalog'),
           ('OTHER','SN001',['DEMO-PRESSURE'],True,'model_not_in_catalog'),
           ('DEMO-EXC','SN002',['DEMO-PRESSURE'],True,'serial_not_applicable'),
           ('DEMO-EXC','SN001',['UNKNOWN'],True,'fault_or_component_not_matched')]
    for model,serial,codes,include,reason in cases:
        report={}
        assert not catalog.search_parts(model,serial,codes,include_demo=include,diagnostics=report)
        assert report['reason_code']==reason
        assert report['returned_count']==0
        assert 'DEMO-SENSOR-1' not in str(report)
    found=catalog.search_parts('DEMO-EXC','SN001',['DEMO-PRESSURE'],include_demo=True,diagnostics=report)
    assert report['reason_code']=='matched' and report['returned_count']==len(found)==1
    assert list(report['counts'].values())==[1,1,1,1,1]
