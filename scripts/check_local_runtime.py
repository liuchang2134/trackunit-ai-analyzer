"""Check local prerequisites without querying Trackunit or printing credentials."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def check(demo_only: bool = False) -> dict:
    required = ("fastapi", "uvicorn", "pydantic", "httpx", "dotenv", "openpyxl", "reportlab")
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if not missing:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=True)
    provider = os.getenv('AI_PROVIDER', 'gemini')
    python_supported = (3,11) <= sys.version_info < (3,14)
    local_ready = python_supported and not missing
    common = {'provider':provider, 'python_supported':python_supported,
              'supported_python':'3.11–3.13', 'missing_dependencies':missing,
              'local_ready':local_ready, 'mode':'local_demo' if demo_only else 'configured_ai',
              'authentication_verified':False}
    if provider == 'gemini':
        configured = bool(os.getenv('GEMINI_API_KEY', '').strip())
        official = os.getenv('GEMINI_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta').rstrip('/') == 'https://generativelanguage.googleapis.com/v1beta'
        ai_ready = local_ready and configured and official
        return {**common, 'model': os.getenv('GEMINI_MODEL', 'gemini-flash-latest'),
                'api_key_configured': configured, 'official_endpoint': official,
                'requires_internet': not demo_only, 'ollama': 'not_required', 'ai_ready':ai_ready,
                'ready': bool(local_ready and official and (demo_only or configured))}
    if provider != 'ollama_local':
        return {**common, 'ai_ready':False, 'ready': False, 'error': 'Unsupported AI provider'}
    model = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    result = {**common,
              "ollama":"not_checked", "model_available":False}
    if demo_only:
        return {**result,'ai_ready':False,'ready':local_ready}
    if urlparse(base).scheme != "http" or urlparse(base).hostname not in {"localhost","127.0.0.1","::1"}:
        result["ollama"]="requires_local_http_address"
    else:
        try:
            with urlopen(base+"/api/tags", timeout=5) as response:
                data=json.load(response)
            names={m.get("name") for m in data.get("models",[])}
            result.update(ollama="reachable",model_available=model in names or model+":latest" in names)
        except Exception:
            result["ollama"]="unavailable"
    result["ready"]=result["python_supported"] and not missing and result["model_available"]
    result['ai_ready']=result['ready']
    return result


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo-only',action='store_true',help='Check local data features without requiring or querying an AI provider')
    report=check(demo_only=parser.parse_args().demo_only)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if report["ready"] else 1)
