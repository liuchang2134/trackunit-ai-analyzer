"""Prepare a clearly synthetic fault-to-parts replay; never touch fleet caches."""
import argparse
from datetime import timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.local_datasets import LocalDataset, save_dataset
from app.models import FaultCode
from app.parts_catalog import CatalogImport, import_catalog


def build_demo() -> LocalDataset:
    dataset = LocalDataset.model_validate_json((ROOT / "docs/examples/excavator-shift.json").read_text(encoding="utf-8"))
    dataset.name = "演示：增压信号告警与备件排查"
    dataset.source_document = "人工编写的告警流程演示；工时沿用模拟片段；不代表真实故障或制造商诊断规则"
    identity = "SIM-PARTS-REPLAY-001"
    dataset.machine.machine_id = identity
    dataset.machine.serial_number = identity
    for row in dataset.telemetry:
        row.machine_id = identity
    dataset.faults = [FaultCode(machine_id=identity, fault_code="ENG-BOOST-102-3",
        description="人工演示告警：增压压力信号异常。可能涉及线路、接头或传感器；尚未确认根因。",
        severity="medium", status="open", occurred_at=(dataset.replay_at-timedelta(minutes=offset)).isoformat())
        for offset in (35, 10)]
    return LocalDataset.model_validate(dataset.model_dump())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Import synthetic dataset and demo catalog into local storage")
    args = parser.parse_args()
    demo = build_demo()
    if args.install:
        catalog = CatalogImport.model_validate_json((ROOT / "docs/examples/demo-parts-catalog.json").read_text(encoding="utf-8"))
        imported = import_catalog(catalog)
        saved = save_dataset(demo)
        print("Local synthetic dataset ID: " + saved["dataset_id"])
        print("Catalog entries added: " + str(imported["added"]))
    else:
        target = ROOT / "docs/examples/excavator-parts-demo.json"
        target.write_text(demo.model_dump_json(indent=2), encoding="utf-8")
        print("Prepared synthetic fault-to-parts demo: " + target.name)
