from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes_assistant import router
from app import history_sync


def client():
    app=FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_route_uses_registered_id_and_bounded_days(monkeypatch):
    calls=[]
    def sync(source,days):
        calls.append((source,days))
        return {"dataset_id":"b"*64,"sample_count":36,"verification":{}}
    monkeypatch.setattr(history_sync,"sync_registered_source",sync)
    c=client()
    response=c.post('/assistant/sync-history',json={"source_id":"a"*64,"days":7})
    assert response.status_code==200 and response.json()["sample_count"]==36
    for payload in [{"source_id":"../secret","days":7},{"source_id":"a"*64,"days":15},
                    {"source_id":"a"*64,"days":True},{"source_id":"a"*64,"endpoint":"https://example.com"}]:
        assert c.post('/assistant/sync-history',json=payload).status_code==422
    assert calls==[("a"*64,7)]


def test_cooldown_is_visible_as_429(monkeypatch):
    def cooldown(*args):raise ValueError("Wait at least 15 minutes")
    monkeypatch.setattr(history_sync,"sync_registered_source",cooldown)
    r=client().post('/assistant/sync-history',json={"source_id":"a"*64,"days":7})
    assert r.status_code==429 and "15" in r.json()["detail"]
