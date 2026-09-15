from datetime import datetime,timedelta,timezone
import pytest
from fastapi.testclient import TestClient
from app import investigation_history as history,inspection_feedback as feedback
from app.main import app


@pytest.fixture
def parent(tmp_path,monkeypatch):
    monkeypatch.setattr(history,'HISTORY_DIR',tmp_path/'history')
    monkeypatch.setattr(feedback,'FEEDBACK_DIR',tmp_path/'feedback')
    return history.save_investigation({'status':'completed','machine_id':'D1','source':'mock',
        'generated_at':'2026-01-01T00:00:00Z','summary':'演示',
        'check_recommendations':[{'check_id':'check:demo','text':'模拟检查'}]},
        {'machine_id':'D1','question':'演示'})


def payload(**changes):
    return {'check_id':'check:demo','outcome':'inconclusive','observed_at':'2026-01-01T12:00:00+08:00',
        'notes':'模拟反馈，未观察实机',**changes}


def test_feedback_roundtrip_and_original_unchanged(parent):
    client=TestClient(app);url='/assistant/history/'+parent['record_id']+'/feedback'
    result=client.post(url,json=payload())
    assert result.status_code==200
    assert result.json()['observed_at']=='2026-01-01T04:00:00Z'
    assert result.json()['source']=='unverified_operator_feedback'
    assert client.get(url).json()['total']==1
    assert history.read_investigation(parent['record_id'])==parent
    assert client.post(url,json=payload(notes='第二条模拟记录')).status_code==200
    assert client.get(url).json()['total']==2


@pytest.mark.parametrize('changes',[
    {'check_id':'foreign-check'}, {'notes':'   '}, {'outcome':'repaired'},
    {'observed_at':'2026-01-01T00:00:00'},
    {'observed_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()},
])
def test_invalid_feedback_rejected(parent,changes):
    client=TestClient(app);url='/assistant/history/'+parent['record_id']+'/feedback'
    assert client.post(url,json=payload(**changes)).status_code==422
    assert client.get(url).json()['total']==0


def test_tampered_feedback_rejected(parent):
    item=feedback.save_feedback(parent['record_id'],feedback.InspectionFeedback(**payload()))
    path=feedback.FEEDBACK_DIR/parent['record_id']/(item['feedback_id']+'.json')
    path.write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='integrity'):feedback.list_feedback(parent['record_id'])
