"""Explicit active pointers, isolated local fixtures; no model or network calls."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app import xgss_research_store as store

VIN = 'XUGTEST000000001'
DATASET = 'a' * 64


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'STORE',tmp_path/'research')


def planned(machine='machine-one',dataset=DATASET,vin=VIN):
    record=store.create(machine,dataset,vin)
    record['plan']={'summary':'本地测试排查计划'}
    store._write(record)
    return record


def identity(record):
    return {key:record[key] for key in ('machine_id','dataset_id','vin')}


def pointer_path(record):
    return store._active_path(identity(record))


def test_only_explicit_activation_restores_exact_record():
    first=planned()
    assert store.active(**identity(first)) is None
    assert store.activate(first['research_id'],None)==first
    later=planned()
    assert store.active(**identity(first))==first
    assert store.activate(later['research_id'],first['research_id'])==later
    assert store.active(**identity(first))==later
    # A retry after a lost response may still contain the old expected ID.
    before=pointer_path(later).read_bytes()
    assert store.activate(later['research_id'],first['research_id'])==later
    assert pointer_path(later).read_bytes()==before


@pytest.mark.parametrize('changes',[{'machine':'machine-two'},{'dataset':'b'*64},
                                    {'dataset':None},{'vin':'XUGOTHER000000001'}])
def test_device_dataset_and_vin_scopes_do_not_leak(changes):
    first=planned()
    other=planned(**changes)
    store.activate(first['research_id'],None)
    assert store.active(**identity(other)) is None
    store.activate(other['research_id'],None)
    assert store.active(**identity(first))==first
    assert store.active(**identity(other))==other


def test_cas_race_has_one_winner_and_rejects_stale_expected_id():
    records=[planned(),planned()]
    barrier=Barrier(2)
    def activate(record):
        barrier.wait(timeout=5)
        try:
            return store.activate(record['research_id'],None)['research_id']
        except store.ActiveResearchConflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(activate,records))
    assert results.count('conflict')==1
    winner=next(value for value in results if value!='conflict')
    assert store.active(**identity(records[0]))['research_id']==winner
    loser=next(record for record in records if record['research_id']!=winner)
    with pytest.raises(store.ActiveResearchConflict):
        store.activate(loser['research_id'],None)
    assert store.activate(loser['research_id'],winner)==loser


@pytest.mark.parametrize('plan',[None,{},'not a plan'])
def test_records_without_a_plan_cannot_be_activated(plan):
    record=store.create('machine-one',DATASET,VIN)
    if plan is not None:
        record['plan']=plan
        store._write(record)
    with pytest.raises(ValueError,match='尚未生成计划'):
        store.activate(record['research_id'],None)
    assert store.active(**identity(record)) is None


def test_latest_stays_separate_and_never_creates_an_active_pointer():
    record=planned()
    assert store.latest(**identity(record))==record
    assert store.active(**identity(record)) is None
    store.activate(record['research_id'],None)
    assert list(store.STORE.glob('*.json'))==[store._path(record['research_id'])]
    assert pointer_path(record).parent==store.STORE/'active'
    assert store.latest(**identity(record))==record


@pytest.mark.parametrize('damage',['missing','wrong_scope','no_plan','invalid_json','bad_page'])
def test_invalid_active_record_fails_without_falling_back(damage):
    record=planned()
    store.activate(record['research_id'],None)
    fallback=planned()
    path=store._path(record['research_id'])
    if damage=='missing':
        path.unlink()
    elif damage=='invalid_json':
        path.write_text('{bad json',encoding='utf-8')
    else:
        if damage=='wrong_scope':record['vin']='XUGOTHER000000001'
        elif damage=='no_plan':record.pop('plan')
        else:record['pages']=[{'content':{'source_url':'https://xgss.xcmg.com/?token=SECRET_SIGNED'}}]
        store._write(record)
    with pytest.raises(ValueError) as failure:
        store.active(**identity(fallback))
    assert 'SECRET_SIGNED' not in str(failure.value)
    # Creating another plan was not enough to change active(). An explicit CAS
    # may repair the reference, but only with the exact old pointer ID.
    with pytest.raises(store.ActiveResearchConflict):store.activate(fallback['research_id'],None)
    assert store.activate(fallback['research_id'],record['research_id'])==fallback
    assert store.active(**identity(fallback))==fallback


@pytest.mark.parametrize('damage',['invalid_json','wrong_scope','extra_url','bad_id'])
def test_pointer_validation_never_echoes_signed_urls(damage):
    record=planned()
    store.activate(record['research_id'],None)
    path=pointer_path(record)
    if damage=='invalid_json':
        path.write_text('https://xgss.xcmg.com/?token=SECRET_SIGNED',encoding='utf-8')
    else:
        pointer=json.loads(path.read_text(encoding='utf-8'))
        if damage=='wrong_scope':pointer['machine_id']='other-machine'
        elif damage=='bad_id':pointer['research_id']='https://xgss.xcmg.com/?token=SECRET_SIGNED'
        else:pointer['signed_url']='https://xgss.xcmg.com/?token=SECRET_SIGNED'
        path.write_text(json.dumps(pointer),encoding='utf-8')
    with pytest.raises(ValueError) as failure:store.active(**identity(record))
    assert 'SECRET_SIGNED' not in str(failure.value)
    assert 'https://' not in str(failure.value)


def test_pointer_only_stores_identity_and_record_id():
    record=planned()
    record['symptom']='本地现场现象，不应复制到指针'
    store._write(record)
    store.activate(record['research_id'],None)
    pointer=json.loads(pointer_path(record).read_text(encoding='utf-8'))
    assert pointer=={**identity(record),'research_id':record['research_id']}


def test_failed_pointer_replace_preserves_previous_active_and_cleans_temp(monkeypatch):
    first,later=planned(),planned()
    store.activate(first['research_id'],None)
    before=pointer_path(first).read_bytes()
    def fail_replace(*args):raise OSError('fixture write failure')
    monkeypatch.setattr(store.os,'replace',fail_replace)
    with pytest.raises(OSError):store.activate(later['research_id'],first['research_id'])
    assert pointer_path(first).read_bytes()==before
    assert list(pointer_path(first).parent.iterdir())==[pointer_path(first)]
    assert store.active(**identity(first))==first
