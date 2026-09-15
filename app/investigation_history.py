"""Immutable local investigation snapshots; no API credentials or live fetches."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

HISTORY_DIR = Path(__file__).resolve().parents[1] / "data/local/investigations"


def save_investigation(report: dict, request: dict) -> dict:
    if report.get("status") != "completed" or report.get("machine_id") != request.get("machine_id"):
        raise ValueError("Only completed matching-machine reports can be saved")
    # Allowlisted user inputs, not arbitrary request/environment serialization.
    inputs = {k: request.get(k) for k in ("machine_id", "dataset_id", "question", "observations", "language", "task", "prior_record_id", "manual_fault")}
    record = {"schema_version": 1, "request": inputs, "report": report}
    content = json.dumps(record, ensure_ascii=False, sort_keys=True)
    record_id = hashlib.sha256(content.encode()).hexdigest()
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=HISTORY_DIR, delete=False) as f:
            temporary = f.name
            f.write(content)
        os.replace(temporary, HISTORY_DIR / (record_id + ".json"))
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return {"record_id": record_id, **record}


def read_investigation(record_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", record_id):
        raise ValueError("Invalid investigation ID")
    try:
        content = (HISTORY_DIR / (record_id + ".json")).read_text(encoding="utf-8")
        if hashlib.sha256(content.encode()).hexdigest() != record_id:
            raise ValueError("Investigation record integrity check failed")
        return {"record_id": record_id, **json.loads(content)}
    except (OSError, json.JSONDecodeError):
        raise ValueError("Investigation record is unavailable") from None


def list_investigations(limit: int = 50, machine_id: str | None = None,
                        dataset_id: str | None = None, source: str | None = None) -> dict:
    records, unreadable = [], 0
    for path in HISTORY_DIR.glob("*.json"):
        try:
            item = read_investigation(path.stem)
            report = item["report"]
            if machine_id is not None and report["machine_id"] != machine_id:
                continue
            if dataset_id is not None and (item["request"].get("dataset_id") or "") != dataset_id:
                continue
            if source is not None and report["source"] != source:
                continue
            records.append({"record_id": item["record_id"], "machine_id": report["machine_id"],
                "generated_at": report["generated_at"], "source": report["source"],
                "dataset_id": item["request"].get("dataset_id"),
                "question": item["request"]["question"], "summary": report["summary"]})
        except (ValueError, KeyError, TypeError):
            unreadable += 1
    records.sort(key=lambda r: r["generated_at"], reverse=True)
    return {"records": records[:limit], "total":len(records), "unreadable":unreadable}
