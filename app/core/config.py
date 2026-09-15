import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _repo_path(value: str, default: str) -> Path:
    path = Path(value or default)
    return path if path.is_absolute() else ROOT / path


class Settings(BaseModel):
    root: Path = ROOT
    data_source: str = os.getenv("DATA_SOURCE", "mock")
    trackunit_cache_ttl_seconds: int = _as_int(os.getenv("TRACKUNIT_CACHE_TTL_SECONDS"), 300)
    trackunit_auto_sync_enabled: bool = _as_bool(os.getenv("TRACKUNIT_AUTO_SYNC_ENABLED"), False)
    trackunit_sync_interval_seconds: int = _as_int(os.getenv("TRACKUNIT_SYNC_INTERVAL_SECONDS"), 300)
    trackunit_auto_sync_run_on_start: bool = _as_bool(os.getenv("TRACKUNIT_AUTO_SYNC_RUN_ON_START"), False)
    sqlite_db_path: Path = _repo_path(os.getenv("SQLITE_DB_PATH", ""), "data/trackunit_ai.db")
    ai_provider: str = os.getenv("AI_PROVIDER", "deepseek")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    gemini_base_url: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")


settings = Settings()
