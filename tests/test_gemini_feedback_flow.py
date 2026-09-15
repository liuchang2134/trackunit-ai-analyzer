"""Application chain with a simulated Gemini HTTP response, not live model evidence."""
import json
from datetime import datetime, timezone
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app import local_datasets, parts_catalog, investigation_history, inspection_feedback
from scripts.prepare_parts_demo import build_demo, ROOT


def test_simulated_gemini_transport_report_feedback_and_continuation(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','simulated-transport-key')
    monkeypatch.setenv('GEMINI_MODEL','gemini-flash-latest')
    monkeypatch.setattr(local_datasets,'DATASETS',tmp_path/'datasets')
    monkeypatch.setattr(parts_catalog,'CATALOG_PATH',tmp_path/'parts.json')
    monkeypatch.setattr(investigation_history,'HISTORY_DIR',tmp_path/'history')
    monkeypatch.setattr(inspection_feedback,'FEEDBACK_DIR',tmp_path/'feedback')
    demo=build_demo()
    dataset=local_datasets.save_dataset(demo)
    catalog=parts_catalog.CatalogImport.model_validate_json((ROOT/'docs/examples/demo-parts-catalog.json').read_text(encoding='utf-8'))
    parts_catalog.import_catalog(catalog)
    calls=[]
    def transport(url, **kwargs):
        assert url.startswith('https://generativelanguage.googleapis.com/v1beta/models/')
        payload=kwargs['json'];calls.append(payload)
        properties=payload['generationConfig']['responseJsonSchema']['properties']
        actions=properties['action']['enum']
        action='parts' if 'parts' in actions else 'finish'
        decision={'action':action,'component':'','summary':'','evidence_ids':[],'next_check_ids':[]}
        if action=='finish':
            decision.update(summary='模拟告警记录需要进一步检查，候选仅为演示资料，根因与整机适配尚未确认。',
                evidence_ids=properties['evidence_ids']['items'].get('enum',[]),
                next_check_ids=properties['next_check_ids']['items'].get('enum',[])[:8])
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(decision,ensure_ascii=False)}]}}]})
    monkeypatch.setattr(httpx,'post',transport)
    client=TestClient(app)
    request={'machine_id':demo.machine.machine_id,'dataset_id':dataset['dataset_id'],
             'question':'检查模拟告警并查询对应目录','task':'parts'}
    first=client.post('/assistant/investigate',json=request)
    assert first.status_code==200, first.text
    report=first.json()
    assert report['history_saved'] and report['provider']=='gemini'
    assert report['ai_status']['last_attempt']['outcome']=='report_saved'
    assert report['parts_candidates'][0]['part_number']=='DEMO-BOOST-SENSOR'
    assert report['parts_candidates'][0]['serial_verified'] is False
    assert all(ref in report['evidence'] for ref in report['citations'])
    record_id=report['record_id']
    original=investigation_history.read_investigation(record_id)
    feedback={'check_id':report['check_recommendations'][0]['check_id'],'outcome':'inconclusive',
              'observed_at':datetime.now(timezone.utc).isoformat(),'notes':'模拟检查：尚未核验连接器，未观察实机。'}
    added=client.post(f'/assistant/history/{record_id}/feedback',json=feedback)
    assert added.status_code==200 and added.json()['source']=='unverified_operator_feedback'
    assert client.get(f'/assistant/history/{record_id}/feedback').json()['total']==1
    next_response=client.post('/assistant/investigate',json={**request,'prior_record_id':record_id})
    assert next_response.status_code==200, next_response.text
    next_report=next_response.json()
    assert next_report['record_id']!=record_id and next_report['prior_record_id']==record_id
    assert next_report['evidence']['operator:feedback']['records'][0]['feedback_id']==added.json()['feedback_id']
    assert investigation_history.read_investigation(record_id)==original
    assert any('模拟检查：尚未核验连接器' in json.dumps(p,ensure_ascii=False) for p in calls)
    before=len(calls)
    rejected=client.post('/assistant/investigate',json={**request,'machine_id':'different-device','prior_record_id':record_id})
    assert rejected.status_code==404 and len(calls)==before
    assert len(list((tmp_path/'history').glob('*.json')))==2
