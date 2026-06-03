from fastapi.testclient import TestClient

from app import main
from app.main import app


def test_ask_api_returns_structure(monkeypatch):
    def fake_answer(question, language="zh", provider_override=None):
        return {
            "question": question,
            "intent": "offline_machines",
            "answer": "M-1003 is offline.",
            "answer_markdown": "M-1003 is offline.",
            "used_data": {"records": [{"machine_id": "M-1003"}]},
            "data_source": "mock",
            "provider": "ollama_local",
            "model": "qwen2.5:7b",
            "error": None,
            "language": "en" if language == "auto" else language,
            "query_plan": {"source": "ai_intent_planner"},
            "intent_plan": {"source": "ai_intent_planner"},
            "data_summary": {"source": "mock", "machines_scanned": 5, "records_used": 1},
            "missing_fields": [],
        }

    monkeypatch.setattr(main, "answer_question", fake_answer)
    client = TestClient(app)
    response = client.post("/ask", json={"question": "Which machines are offline?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "offline_machines"
    assert payload["answer"] == "M-1003 is offline."
    assert payload["data_source"] == "mock"
    assert payload["model"] == "qwen2.5:7b"
    assert payload["data_summary"]["machines_scanned"] == 5


def test_ask_api_accepts_ai_provider(monkeypatch):
    def fake_answer(question, language="zh", provider_override=None):
        return {
            "question": question,
            "intent": "low_fuel",
            "answer": "低油量设备。",
            "answer_markdown": "低油量设备。",
            "used_data": {"records": []},
            "data_source": "mock",
            "provider": provider_override,
            "model": "gemini-flash-latest",
            "error": None,
            "language": "zh",
            "query_plan": {"source": "ai_intent_planner"},
            "intent_plan": {"source": "ai_intent_planner"},
            "data_summary": {"source": "mock", "machines_scanned": 5, "records_used": 0},
            "missing_fields": [],
        }

    monkeypatch.setattr(main, "answer_question", fake_answer)
    client = TestClient(app)
    response = client.post("/ask", json={"question": "哪些设备快没油了", "ai_provider": "gemini"})

    assert response.status_code == 200
    assert response.json()["provider"] == "gemini"
