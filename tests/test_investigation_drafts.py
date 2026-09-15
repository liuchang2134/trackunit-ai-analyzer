from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app import investigation_drafts as drafts
from app.main import app


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(drafts, 'DRAFT_DIR', tmp_path/'drafts')
    machine = SimpleNamespace(machine_id='SIM-A', serial_number='SIM-A', model='SIM-EXC')
    monkeypatch.setattr(drafts, 'find_machine', lambda key: machine if key=='SIM-A' else None)
    monkeypatch.setattr(drafts, 'get_data_source', lambda:'mock')
    monkeypatch.setattr(drafts, 'load_dataset', lambda key: SimpleNamespace(machine=machine, provenance='synthetic'))
    return TestClient(app)


def payload(**extra):
    return dict(machine_id='SIM-A', dataset_id=None, source='mock', expected_revision=None,
                content={'question':'检查模拟故障', 'observations':'未检查压力信号。\n  保留原文  ',
                         'task':'parts','language':'zh','prior_record_id':None}, **extra)


def test_saved_before_ai_and_read_again(local, monkeypatch):
    from app import gemini_client, local_assistant
    monkeypatch.setattr(local_assistant,'investigate',lambda *a:pytest.fail('No investigation'))
    monkeypatch.setattr(gemini_client,'generate_structured_with_gemini',lambda *a,**k:pytest.fail('No cloud'))
    scope={'machine_id':'SIM-A','source':'mock'}
    assert local.get('/assistant/draft',params=scope).json()['draft'] is None
    result=local.put('/assistant/draft',json=payload())
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    record=result.json()['draft']
    assert record['content']==payload()['content']
    assert record['source_kind']=='unverified_operator_draft' and result.json()['ai_used'] is False
    assert local.get('/assistant/draft',params=scope).json()['draft']==record
    assert not list(drafts.DRAFT_DIR.parent.glob('investigations/*.json'))


def manual_code(code='H10101'):
    return {'code':code,'model':'TV12U','version':'260224','applicability_confirmed':True}


def test_code_only_draft_survives_missing_reference_and_does_not_invoke_ai(local, monkeypatch):
    from app import fault_reference, gemini_client
    monkeypatch.setattr(drafts,'find_machine',lambda _:SimpleNamespace(machine_id='SIM-A',serial_number='SIM-A',model='TV12U'))
    monkeypatch.setattr(fault_reference,'load_reference',lambda *a,**k:pytest.fail('Saving operator input must not require lookup'))
    monkeypatch.setattr(gemini_client,'generate_structured_with_gemini',lambda *a,**k:pytest.fail('No cloud'))
    body=payload();body['content'].update(question='',observations='',manual_fault=manual_code())
    saved=local.put('/assistant/draft',json=body)
    assert saved.status_code==200 and saved.json()['ai_used'] is False
    record=saved.json()['draft']
    assert record['content']['manual_fault']==manual_code()
    assert record['source_kind']=='unverified_operator_draft'
    assert local.get('/assistant/draft',params={'machine_id':'SIM-A','source':'mock'}).json()['draft']==record
    body['expected_revision']=record['revision'];body['content'].update(manual_fault=None,question='移除人工故障码')
    removed=local.put('/assistant/draft',json=body)
    assert removed.status_code==200 and 'manual_fault' not in removed.json()['draft']['content']


def test_wrong_model_code_cannot_overwrite_existing_draft(local):
    first=local.put('/assistant/draft',json=payload()).json()['draft']
    body=payload();body['expected_revision']=first['revision'];body['content']['manual_fault']=manual_code()
    response=local.put('/assistant/draft',json=body)
    assert response.status_code==404
    assert local.get('/assistant/draft',params={'machine_id':'SIM-A','source':'mock'}).json()['draft']==first


@pytest.mark.parametrize('changes',[
    {'code':'SPN10101'},{'version':'250224'},{'model':'XE55U'},
    {'applicability_confirmed':False},{'applicability_confirmed':1},{'secret':'forbidden'}])
def test_draft_manual_code_contract_is_not_relaxed(local,changes):
    body=payload();body['content']['manual_fault']={**manual_code(),**changes}
    assert local.put('/assistant/draft',json=body).status_code==422


def test_dataset_and_source_isolation(local):
    first=local.put('/assistant/draft',json=payload()).json()['draft']
    body=payload(); body.update(dataset_id='a'*64,source='imported_synthetic')
    second=local.put('/assistant/draft',json=body)
    assert second.status_code==200 and second.json()['draft']['scope']!=first['scope']
    assert local.get('/assistant/draft',params={'machine_id':'SIM-A','source':'imported_synthetic','dataset_id':'b'*64}).json()['draft'] is None
    assert local.get('/assistant/draft',params={'machine_id':'SIM-A','source':'trackunit_cache'}).status_code==404
    body['machine_id']='SIM-B'
    assert local.put('/assistant/draft',json=body).status_code==404


def test_stale_concurrent_save_cannot_replace_a_newer_revision(local):
    first=local.put('/assistant/draft',json=payload()).json()['draft']
    body=payload();body['expected_revision']=first['revision']
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:local.put('/assistant/draft',json=body),range(2)))
    assert sorted(r.status_code for r in responses)==[200,409]
    assert local.put('/assistant/draft',json=payload()).status_code==409


def test_failed_write_preserves_last_saved_version(local,monkeypatch):
    first=local.put('/assistant/draft',json=payload()).json()['draft']
    body=payload();body['expected_revision']=first['revision'];body['content']['observations']='new'
    def fail(*args):raise OSError('private path must not escape')
    monkeypatch.setattr(drafts.os,'replace',fail)
    response=local.put('/assistant/draft',json=body)
    assert response.status_code==503 and 'private path' not in response.text
    assert local.get('/assistant/draft',params={'machine_id':'SIM-A','source':'mock'}).json()['draft']==first


def test_corrupt_record_does_not_silently_reset_revision(local):
    local.put('/assistant/draft',json=payload())
    path=next(drafts.DRAFT_DIR.glob('*.json'))
    saved=json.loads(path.read_text(encoding='utf-8'));saved['content']['observations']='changed'
    path.write_text(json.dumps(saved),encoding='utf-8')
    scope={'machine_id':'SIM-A','source':'mock'}
    assert local.get('/assistant/draft',params=scope).status_code==503
    assert local.put('/assistant/draft',json=payload()).status_code==503


def test_prior_report_must_belong_to_the_device_and_source(local,monkeypatch):
    body=payload();body['content']['prior_record_id']='d'*64
    monkeypatch.setattr(drafts,'read_investigation',lambda _: {'request':{'dataset_id':None},'report':{'machine_id':'SIM-B','source':'mock'}})
    assert local.put('/assistant/draft',json=body).status_code==404
    monkeypatch.setattr(drafts,'read_investigation',lambda _: {'request':{'dataset_id':None},'report':{'machine_id':'SIM-A','source':'trackunit'}})
    assert local.put('/assistant/draft',json=body).status_code==404


@pytest.mark.parametrize('changes',[
    {'content':{'question':'','observations':'  '}},
    {'content':{'question':'q','observations':'x'*4001}},
    {'content':{'question':'q','secret':'forbidden'}},
    {'dataset_id':'../../outside'}, {'expected_revision':'bad'}])
def test_invalid_input_rejected(local,changes):
    body=payload();body.update(changes)
    assert local.put('/assistant/draft',json=body).status_code==422
