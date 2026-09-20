"""The demo scenario must keep the whole flow walkable, and stay visibly synthetic.

The flow is identity -> telemetry -> fault code -> manual reasoning. A real fleet has no
broken machines, and none of the machines in the mock fleet is an XE55U, so without this
scenario the manual step answers nothing.

It ships as its own data source (`DATA_SOURCE=demo`, `app/demo_data/`) rather than an extra
machine in `app/mock_data/`: the mock fleet is the fixture the offline walkthrough and many
tests depend on, and a second XE55U in it would silently make model-based lookups ambiguous.

These tests hold two things in place: that the scenario still feeds every step, and that a
reviewer can tell which parts were generated.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / 'app/demo_data'
DEMO_ID = 'DEMO-XE55U-001'
DEMO_MODEL = 'XE55U'
DEMO_CODE = 'E4030'
MANUAL_PUBLIC = ROOT / 'data/demo/manual-knowledge/xe55u.json'


def rows(name: str) -> list:
    path = DEMO_DIR / name
    if not path.is_file():
        pytest.skip(f'{name} missing; run scripts/prepare_demo_scenario.py')
    return json.loads(path.read_text(encoding='utf-8'))


def demo_machine():
    return next((row for row in rows('machines.json') if row.get('machine_id') == DEMO_ID), None)


def demo_telemetry():
    return [row for row in rows('telemetry_snapshots.json') if row.get('machine_id') == DEMO_ID]


def demo_fault():
    return next((row for row in rows('fault_codes.json') if row.get('machine_id') == DEMO_ID), None)


def test_the_scenario_machine_exists_and_can_reach_the_manual_step():
    machine = demo_machine()
    assert machine is not None, 'the demo machine is missing; run scripts/prepare_demo_scenario.py'
    # The manual excerpts cover this model and code only. Another model would demonstrate
    # the empty-answer path instead of the reasoning path.
    assert machine['model'] == DEMO_MODEL


def test_the_scenario_has_telemetry_and_a_fault_event():
    assert len(demo_telemetry()) >= 10, 'a fault with no history cannot show a trend'
    fault = demo_fault()
    assert fault is not None, 'the demo needs a fault event or step two has nothing to read'
    assert fault['fault_code'] == DEMO_CODE and fault['status'] == 'open'


def test_the_machine_says_it_is_synthetic():
    machine = demo_machine()
    assert machine['machine_id'].startswith('DEMO-'), 'the id must read as a demo machine'
    assert machine['serial_number'].startswith('SIM-'), 'the serial must read as simulated'


def test_the_fault_says_it_was_generated_not_reported():
    # A fault on someone's real machine would be fabrication. The marker travels with the
    # record so a consumer can tell without trusting a caption on a slide.
    fault = demo_fault()
    payload = fault.get('raw_payload') or {}
    assert payload.get('scenario') == 'synthetic_scenario'
    assert payload.get('not_a_trackunit_report') is True
    assert '合成' in fault['description'] and '非平台上报' in fault['description']


def test_the_scenario_files_use_the_model_field_names():
    # These files are read straight into the pydantic models, unlike app/mock_data/ which
    # goes through the normalizer's camelCase mapping. A camelCase field here would fail
    # validation at runtime rather than at prepare time.
    machine = demo_machine()
    assert set(machine) >= {'machine_id', 'serial_number', 'model', 'last_seen_at'}
    assert 'id' not in machine and 'serialNumber' not in machine
    telemetry = demo_telemetry()[0]
    assert 'recorded_at' in telemetry and 'recordedAt' not in telemetry
    fault = demo_fault()
    assert 'fault_code' in fault and 'code' not in fault


def test_the_scenario_is_isolated_from_the_mock_fleet():
    # Sharing the mock fixture would change what every other test and the offline
    # walkthrough see, which is why this is a separate source.
    mock = json.loads((ROOT / 'app/mock_data/machines.json').read_text(encoding='utf-8'))
    assert all(row.get('id') != DEMO_ID for row in mock), \
        'the demo machine must not be added to the mock fleet'
    assert all(row.get('model') != DEMO_MODEL for row in mock), \
        'the mock fleet has no XE55U; that is what makes a separate demo source necessary'


def test_the_data_store_exposes_a_demo_source():
    source = (ROOT / 'app/data_store.py').read_text(encoding='utf-8')
    assert "if configured == \"demo\":" in source
    assert 'DEMO_MACHINES' in source and 'DEMO_TELEMETRY' in source and 'DEMO_FAULTS' in source
    for name in ('machines.json', 'telemetry_snapshots.json', 'fault_codes.json'):
        assert (DEMO_DIR / name).is_file(), f'{name} missing from the demo source'


def test_the_manual_excerpts_are_distributable():
    # Without this copy the scenario only works on a machine that has the private manual.
    assert MANUAL_PUBLIC.is_file(), 'run scripts/prepare_demo_scenario.py to publish the excerpts'
    payload = json.loads(MANUAL_PUBLIC.read_text(encoding='utf-8-sig'))
    assert payload['schema_version'] == 1
    records = payload['records']
    assert records, 'a published manual with no records demonstrates nothing'
    pages = sorted({page for record in records for page in record.get('pdf_pages', [])})
    assert pages == [286, 287], f'the excerpts must cover the pages the demo cites, got {pages}'
    for record in records:
        assert DEMO_CODE in record.get('fault_codes', []), 'excerpts must match the demo fault code'
        assert record.get('text'), 'an excerpt without text cannot ground an answer'


def test_the_reader_falls_back_to_the_published_excerpts():
    from app import manual_knowledge

    assert manual_knowledge._PUBLIC_KNOWLEDGE.is_file()
    # The private copy wins where it exists; the published copy keeps a machine without it
    # able to demonstrate the reasoning step.
    chosen = manual_knowledge.knowledge_path()
    assert chosen in (manual_knowledge._PRIVATE_KNOWLEDGE, manual_knowledge._PUBLIC_KNOWLEDGE)
    assert chosen.is_file()


def test_the_scenario_documentation_states_the_provenance():
    note = (ROOT / 'data/demo/SCENARIO.md').read_text(encoding='utf-8')
    assert DEMO_ID in note and DEMO_CODE in note
    assert '合成' in note and '真实' in note, 'the note must separate generated from real'
    assert 'DATA_SOURCE=demo' in note, 'the note must say how to enable the scenario'
