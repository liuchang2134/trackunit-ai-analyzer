"""Contract/data isolation tests; synthetic fixtures are not equipment definitions."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import fault_reference as ref
from app.api.routes_fault_reference import router


@pytest.fixture
def raw_reference():
    raw = {
        'reference_id': ref.REFERENCE_ID, 'model_from_filename': 'TV12U',
        'protocol_version_from_filename': '260224', 'source_sheet': ref.SOURCE_SHEET,
        'source_range': 'A1:H129', 'source_type': 'user_provided_protocol',
        'source_sha256': ref.SOURCE_SHA256, 'reminder_modes': dict(ref.REMINDER_MODES),
        'source_path': 'C:/PRIVATE/source.xlsx', 'raw_fault_sheet': {'secret': 'DO_NOT_EXPOSE'},
        'faults': [],
    }
    for prefix, count, can_id, first_row in [('E', 30, '0x11F501A1', 2), ('H', 42, '0x11F501A2', 66)]:
        for index in range(count):
            row = first_row + index
            code = f'{prefix}{10101 + index}'
            raw['faults'].append({
                'code': code, 'can_id': can_id, 'byte_index': index // 8,
                'bit_index': index % 8, 'source_row': row,
                'description': '测试故障定义', 'display_prompt': '测试显示提示',
                'display_rule_raw': '0/1', 'display_text_raw': f'不显示/显示{code}',
                'reminder_mode': 1, 'reminder_description': ref.REMINDER_MODES['1'],
                'source_cells': {col: f'{col}{row}' for col in 'ABCDEFGH'},
            })
    raw['faults'][0]['description'] = '脚油门踏板传感器1开路'
    raw['faults'][30].update(description='左泵前进比例阀短路', display_prompt='左泵前进比例阀故障',
                             reminder_mode=3, reminder_description=ref.REMINDER_MODES['3'])
    return raw


@pytest.fixture
def installed(raw_reference, tmp_path, monkeypatch):
    # Synthetic fixture has its own pinned digest; production reference stays pinned separately.
    monkeypatch.setattr(ref, 'CONTENT_SHA256', '183ac29f5ec2a6b791dfd410b6700122c1bd823c992043c5b4b7888b808044a5')
    path = tmp_path / 'reference.json'
    path.write_text(json.dumps(raw_reference, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setenv('TV12U_FAULT_REFERENCE_PATH', str(path))
    return path


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_scoped_lookup_preserves_original_evidence_without_paths(installed):
    catalog = ref.load_reference()
    item = ref.lookup_fault(catalog, model='tv12u', version='260224', code=' h10101 ')
    assert item['description'] == '左泵前进比例阀短路'
    assert item['reminder_mode'] == 3 and item['reminder_description'] == '常显示代码，蜂鸣器持续提醒'
    assert (item['can_id'], item['byte_index'], item['bit_index'], item['source_row']) == ('0x11F501A2', 0, 0, 66)
    assert item['source_sheet'] == ref.SOURCE_SHEET
    assert item['source_cells']['F'] == 'F66'
    assert not {'severity', 'part_number', 'repair_steps', 'spn', 'fmi'}.intersection(item)
    item['source_cells']['F'] = 'F99'
    assert catalog['items'][30]['source_cells']['F'] == 'F66'
    assert 'PRIVATE' not in json.dumps(catalog) and 'DO_NOT_EXPOSE' not in json.dumps(catalog)


@pytest.mark.parametrize('model,version', [('XE55U', '260224'), ('TV12U-II', '260224'), ('TV12U', '250224')])
def test_never_applies_reference_to_another_model_or_version(installed, model, version):
    with pytest.raises(ValueError):
        ref.lookup_fault(ref.load_reference(), model=model, version=version, code='H10101')


def test_search_returns_original_codes_without_guessing_near_match(installed):
    catalog = ref.load_reference()
    assert len(ref.search_faults(catalog, model='TV12U', version='260224')) == 72
    assert [r['code'] for r in ref.search_faults(catalog, model='TV12U', version='260224', q='左泵')] == ['H10101']
    assert ref.lookup_fault(catalog, model='TV12U', version='260224', code='H99999') is None
    with pytest.raises(ValueError):
        ref.lookup_fault(catalog, model='TV12U', version='260224', code='SPN10101')


@pytest.mark.parametrize('field,value', [
    ('byte_index', 8), ('bit_index', -1), ('bit_index', True), ('source_row', 999),
    ('can_id', '0x11F501A2'), ('description', ''), ('reminder_mode', 4),
    ('reminder_description', 'HIGH_RISK'), ('display_text_raw', '不显示/显示OTHER'),
    ('source_cells', {'A': 'A2'}),
])
def test_invalid_evidence_fails_closed(raw_reference, field, value):
    raw_reference['faults'][0][field] = value
    with pytest.raises(ref.ReferenceUnavailable, match='校验失败'):
        ref.validate_reference(raw_reference)


def test_duplicate_code_or_position_and_incomplete_catalog_rejected(raw_reference):
    duplicate_code = deepcopy(raw_reference)
    duplicate_code['faults'][1]['code'] = 'E10101'
    duplicate_position = deepcopy(raw_reference)
    duplicate_position['faults'][1].update(byte_index=0, bit_index=0, source_row=2)
    incomplete = deepcopy(raw_reference)
    incomplete['faults'].pop()
    for invalid in (duplicate_code, duplicate_position, incomplete):
        with pytest.raises(ref.ReferenceUnavailable):
            ref.validate_reference(invalid)


def test_missing_or_corrupt_data_is_explicit_not_empty_success(installed, client):
    installed.unlink()
    result = client.get('/assistant/fault-reference/status')
    assert result.status_code == 200 and result.json()['reason'] == 'missing'
    assert result.json()['available'] is False
    result = client.get('/assistant/fault-reference', params={'model': 'TV12U', 'version': '260224'})
    assert result.status_code == 503
    installed.write_text('{bad json', encoding='utf-8')
    assert client.get('/assistant/fault-reference/status').json()['reason'] == 'invalid'
    assert str(installed) not in client.get('/assistant/fault-reference/status').text


def test_edited_definition_cannot_reuse_source_provenance(installed, client):
    original = json.loads(installed.read_text(encoding='utf-8'))
    original['faults'][0]['description'] = '改写的定义，不能继续标为源表原文'
    installed.write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
    assert client.get('/assistant/fault-reference/status').json()['reason'] == 'invalid'
    assert client.get('/assistant/fault-reference', params={'model': 'TV12U', 'version': '260224'}).status_code == 503


def test_api_list_search_exact_status_and_invalid_scope(installed, client):
    status = client.get('/assistant/fault-reference/status')
    assert status.json()['fault_count'] == 72 and status.json()['offline'] is True
    params = {'model': 'TV12U', 'version': '260224'}
    result = client.get('/assistant/fault-reference', params=params)
    assert result.status_code == 200 and result.json()['total'] == 72
    assert result.headers['cache-control'] == 'no-store'
    assert 'source_path' not in result.text and 'raw_fault_sheet' not in result.text
    assert client.get('/assistant/fault-reference', params={**params, 'q': '左泵'}).json()['total'] == 1
    assert client.get('/assistant/fault-reference', params={**params, 'q': '不存在'}).json()['total'] == 0
    assert client.get('/assistant/fault-reference', params={**params, 'code': 'H10101'}).json()['items'][0]['source_row'] == 66
    assert client.get('/assistant/fault-reference', params={**params, 'code': 'H99999'}).status_code == 404
    assert client.get('/assistant/fault-reference', params={**params, 'model': 'XE55U'}).status_code == 422
    assert client.get('/assistant/fault-reference', params={**params, 'code': 'H10101', 'q': ''}).status_code == 422
    assert client.get('/assistant/fault-reference').status_code == 422


def test_installed_user_reference_matches_known_sheet_cells():
    if not Path(ref.REFERENCE_PATH).is_file():
        pytest.skip('User supplied TV12U reference is not distributed with the test suite')
    catalog = ref.load_reference(ref.REFERENCE_PATH)
    assert len(catalog['items']) == 72
    assert ref.lookup_fault(catalog, model='TV12U', version='260224', code='E10101')['description'] == '脚油门踏板传感器1开路'
    fault = ref.lookup_fault(catalog, model='TV12U', version='260224', code='H10101')
    assert fault['description'] == '左泵前进比例阀短路' and fault['source_cells']['H'] == 'H66'
