"""Isolated, content-addressed telemetry imports; never overwrite Trackunit caches."""
import csv
import hashlib
import io
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.models import Machine, TelemetrySnapshot, FaultCode
from app.telemetry_evidence import timestamp, number

DATASETS = Path(__file__).resolve().parents[1] / "data" / "local" / "datasets"


class CoolingReference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    episode_id: str = Field(pattern=r'^CW-[0-9a-f]{12}$')
    cursor: int = Field(ge=0,le=479,strict=True)
    model_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class LocalDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    source_document: str = Field(min_length=1, max_length=300)
    provenance: Literal["synthetic", "user_supplied"]
    machine: Machine
    telemetry: list[TelemetrySnapshot] = Field(min_length=1, max_length=10000)
    faults: list[FaultCode] = Field(default_factory=list, max_length=1000)
    replay_at: datetime | None = None
    cooling_reference: CoolingReference | None = None

    @model_validator(mode="after")
    def validate_records(self):
        if self.cooling_reference is not None and self.provenance!='synthetic':
            raise ValueError('Cooling demonstration requires synthetic provenance')
        if self.replay_at is not None:
            if self.provenance != "synthetic" or self.replay_at.tzinfo is None:
                raise ValueError("replay_at is timezone-aware and only allowed for synthetic datasets")
        for row in [*self.telemetry, *self.faults]:
            if row.machine_id != self.machine.machine_id:
                raise ValueError("Every record must belong to the declared machine")
            dt = timestamp(row.recorded_at if isinstance(row, TelemetrySnapshot) else row.occurred_at)
            if dt is None:
                raise ValueError("Records require ISO timestamps with timezone")
            if self.replay_at is not None and dt > self.replay_at:
                raise ValueError("Records after replay_at are not permitted")
            if row.raw_payload is not None:
                raise ValueError("Import normalized records only; raw_payload is not supported")
        for row in self.telemetry:
            for value in (row.operating_hours, row.idle_hours):
                if value is not None and (not number(value) or value < 0):
                    raise ValueError("Hour counters must be finite and nonnegative")
            if row.fuel_remaining_percent is not None and (not number(row.fuel_remaining_percent) or not 0 <= row.fuel_remaining_percent <= 100):
                raise ValueError("Fuel percent must be between 0 and 100")
        self.telemetry.sort(key=lambda r: timestamp(r.recorded_at))
        self.faults.sort(key=lambda r: timestamp(r.occurred_at))
        return self


class CsvDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    source_document: str = Field(min_length=1, max_length=300)
    provenance: Literal["synthetic", "user_supplied"]
    machine: Machine
    csv_text: str = Field(min_length=1, max_length=3_000_000)
    replay_at: datetime | None = None


def parse_csv(request: CsvDatasetRequest) -> LocalDataset:
    reader = csv.DictReader(io.StringIO(request.csv_text.lstrip("\ufeff")))
    allowed = {"recorded_at", "operating_hours", "idle_hours", "fuel_remaining_percent", "engine_status"}
    names = reader.fieldnames or []
    if not names or "recorded_at" not in names or len(names) != len(set(names)) or set(names) - allowed:
        raise ValueError("CSV requires recorded_at and only supported normalized columns")
    rows = []
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("CSV row length does not match header")
        if len(rows) >= 10000:
            raise ValueError("CSV supports at most 10000 rows")
        clean = {key: value.strip() for key, value in row.items() if value.strip()}
        rows.append(TelemetrySnapshot(machine_id=request.machine.machine_id, **clean))
    return LocalDataset(**request.model_dump(exclude={"csv_text"}), telemetry=rows)


def save_dataset(dataset: LocalDataset) -> dict:
    content = dataset.model_dump_json()
    dataset_id = hashlib.sha256(content.encode()).hexdigest()
    DATASETS.mkdir(parents=True, exist_ok=True)
    path = DATASETS / f"{dataset_id}.json"
    if not path.exists():
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=DATASETS, delete=False) as f:
                temporary = f.name
                f.write(content)
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    return dataset_summary(dataset_id, dataset)


def load_dataset(dataset_id: str) -> LocalDataset:
    if not re.fullmatch(r"[0-9a-f]{64}", dataset_id):
        raise ValueError("Invalid dataset ID")
    path = DATASETS / f"{dataset_id}.json"
    if not path.is_file():
        raise ValueError("Dataset not found")
    return LocalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def dataset_summary(dataset_id: str, dataset: LocalDataset) -> dict:
    cutoff = dataset.replay_at or datetime.now(timezone.utc)
    latest = max((dt for row in dataset.telemetry
                  if (dt := timestamp(row.recorded_at)) is not None and dt <= cutoff), default=None)
    return {"dataset_id": dataset_id, "name": dataset.name, "provenance": dataset.provenance,
            "machine": dataset.machine.model_dump(), "sample_count": len(dataset.telemetry),
            "latest_telemetry_at": latest.isoformat() if latest else None,
            "source_document": dataset.source_document,
            "cooling_reference": dataset.cooling_reference.model_dump() if dataset.cooling_reference else None,
            "replay_at": dataset.replay_at.isoformat() if dataset.replay_at else None}


def list_datasets() -> list[dict]:
    result = []
    for path in sorted(DATASETS.glob("*.json")):
        if not re.fullmatch(r"[0-9a-f]{64}", path.stem):
            continue
        result.append(dataset_summary(path.stem, load_dataset(path.stem)))
    return result
