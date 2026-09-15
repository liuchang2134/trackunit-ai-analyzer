"""Keep unit tests independent of local credentials and data configuration."""
import os
import pytest
os.environ["PYTHON_DOTENV_DISABLED"] = "1"


@pytest.fixture(autouse=True)
def isolated_ai_configuration(monkeypatch, tmp_path):
    from app import ai_request_status, investigation_drafts, maintenance_cases
    monkeypatch.setattr(maintenance_cases, 'CASE_DB', tmp_path / 'maintenance-cases.sqlite3')
    monkeypatch.setattr(investigation_drafts, 'DRAFT_DIR', tmp_path / 'investigation-drafts')
    monkeypatch.setattr(ai_request_status, 'STATUS_PATH', tmp_path / 'ai-request-status.json')
    monkeypatch.setenv('AI_PROVIDER', 'ollama_local')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
