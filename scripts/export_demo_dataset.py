"""Convert a public simulator episode to the sidebar import format, without labels/truth."""
import csv
from datetime import datetime, timedelta
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.local_datasets import LocalDataset


def convert(episode_path: Path) -> LocalDataset:
    metadata = json.loads(episode_path.read_text(encoding="utf-8"))
    cutoff = datetime.fromisoformat(metadata["start_utc"]) + timedelta(seconds=metadata["decision_s"])
    rows = []
    with gzip.open(episode_path.parent / "telemetry.csv.gz", "rt", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row["recorded_at"]:
                continue
            if datetime.fromisoformat(row["observed_at"]) > cutoff:
                continue
            rows.append({"machine_id": metadata["machine_id"], "recorded_at": row["recorded_at"],
                "operating_hours": float(row["operating_hours"]) if row["operating_hours"] else None,
                "idle_hours": float(row["idle_hours"]) if row["idle_hours"] else None,
                "fuel_remaining_percent": float(row["fuel_percent"]) if row["fuel_percent"] else None,
                "engine_status": row["engine_status"] or "unknown"})
    if len(rows) < 2:
        raise ValueError("Episode lacks two usable samples")
    return LocalDataset.model_validate({"name": "柴油液压挖掘机 · 模拟工况片段",
        "source_document": f"synthetic_diagnostics_v1/public/train/{metadata['episode_id']}; simulator assumptions, not measured data",
        "provenance": "synthetic", "replay_at": cutoff.isoformat(),
        "machine": {"machine_id": metadata["machine_id"], "serial_number": metadata["machine_id"],
            "model": "XE135U", "machine_type": "excavator", "customer": "SYNTHETIC DEMO",
            "location": "Synthetic site", "last_seen_at": max(r["recorded_at"] for r in rows)},
        "telemetry": rows, "faults": []})


if __name__ == "__main__":
    candidates = sorted((ROOT / "data/synthetic_diagnostics_v1/public/train").glob("*/episode.json"))
    if not candidates:
        raise SystemExit("Generate the synthetic dataset first")
    dataset = convert(candidates[0])
    target = ROOT / "docs/examples/excavator-shift.json"
    target.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")
    print(f"Created {target.name}: {len(dataset.telemetry)} samples; synthetic; public observations only")
