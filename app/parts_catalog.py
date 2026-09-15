"""Local catalog: applicability is a constraint, never a language-model guess."""
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "local" / "parts.json"
_lock = threading.Lock()


class CatalogPart(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    part_number: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=240)
    component: str = Field(min_length=1, max_length=120)
    models: list[str] = Field(min_length=1, max_length=100)
    serial_numbers: list[str] = Field(default_factory=list, max_length=2000)
    applicability: Literal["model_only", "serial_list"] = "model_only"
    fault_codes: list[str] = Field(default_factory=list, max_length=100)
    checks: list[str] = Field(min_length=1, max_length=20)
    source_document: str = Field(min_length=1, max_length=240)
    source_page: str = Field(min_length=1, max_length=80)
    revision: str = Field(min_length=1, max_length=80)
    provenance: Literal["demo", "user_supplied"]

    @field_validator("models", "serial_numbers", "fault_codes", "checks")
    @classmethod
    def clean_entries(cls, values):
        if any(not item.strip() or len(item) > 600 for item in values):
            raise ValueError("Entries must be nonempty and at most 600 characters")
        return list(dict.fromkeys(item.strip() for item in values))

    @model_validator(mode="after")
    def serial_scope(self):
        if self.applicability == "serial_list" and not self.serial_numbers:
            raise ValueError("serial_list requires explicit serial_numbers")
        if self.applicability == "model_only" and self.serial_numbers:
            raise ValueError("Use serial_list when serial restrictions are provided")
        if self.provenance == "demo" and not self.part_number.startswith("DEMO-"):
            raise ValueError("Demo identifiers must begin with DEMO-")
        return self


class CatalogImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parts: list[CatalogPart] = Field(max_length=5000)

    @model_validator(mode="after")
    def unique_numbers(self):
        keys = [p.part_number.casefold() for p in self.parts]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate part numbers; consolidate applicability into one record")
        return self


def load_catalog() -> CatalogImport:
    if not CATALOG_PATH.exists():
        return CatalogImport(parts=[])
    return CatalogImport.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))


def import_catalog(payload: CatalogImport) -> dict:
    """Merge by exact part number; reject conflicts instead of silently replacing data."""
    with _lock:
        current = {p.part_number.casefold(): p for p in load_catalog().parts}
        added = 0
        for part in payload.parts:
            key = part.part_number.casefold()
            if key in current and current[key] != part:
                raise ValueError(f"Conflicting part number: {part.part_number}")
            if key not in current:
                current[key] = part
                added += 1
        merged = CatalogImport(parts=list(current.values()))
        CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=CATALOG_PATH.parent, delete=False) as handle:
                name = handle.name
                handle.write(merged.model_dump_json(indent=2))
            os.replace(name, CATALOG_PATH)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
        return {"added": added, "total": len(current)}


def search_parts(model: str, serial_number: str = "", fault_codes: list[str] | None = None,
                 component: str = "", include_demo: bool = False, *, diagnostics: dict | None = None) -> list[dict]:
    codes = {code.casefold() for code in fault_codes or []}
    result = []
    parts = load_catalog().parts
    counts = {'catalog_entries':len(parts),'eligible_provenance':0,'matching_model':0,'matching_serial_scope':0,'matching_query':0}
    for part in parts:
        if part.provenance == "demo" and not include_demo:
            continue
        counts['eligible_provenance'] += 1
        if model.casefold() not in {m.casefold() for m in part.models}:
            continue
        counts['matching_model'] += 1
        if part.applicability == "serial_list" and serial_number.casefold() not in {s.casefold() for s in part.serial_numbers}:
            continue
        counts['matching_serial_scope'] += 1
        code_match = bool(codes & {c.casefold() for c in part.fault_codes})
        component_match = bool(component.strip()) and component.casefold() in part.component.casefold()
        if not code_match and not component_match:
            continue
        counts['matching_query'] += 1
        result.append({**part.model_dump(), "status": "candidate_requires_inspection",
                       "match_reason": "fault_code" if code_match else "component",
                       "serial_verified": part.applicability == "serial_list",
                       "source_id": f"catalog:{part.part_number}",
                       "limitation": "Verify machine configuration and inspection results before ordering."})
    if diagnostics is not None:
        explanations = [
            ('catalog_entries','catalog_empty','The local catalog contains no entries.'),
            ('eligible_provenance','no_eligible_catalog','All catalog entries are demonstration-only and excluded for this data source.'),
            ('matching_model','model_not_in_catalog','No eligible catalog entry lists the exact equipment model.'),
            ('matching_serial_scope','serial_not_applicable','Model entries exist, but none permit this serial number under their applicability constraints.'),
            ('matching_query','fault_or_component_not_matched','Entries passed the model and serial-scope filters, but none match the supplied fault codes or component query. Passing filters does not verify machine configuration; entries without a serial restriction do not verify serial applicability.')]
        failure=next(((code,meaning) for stage,code,meaning in explanations if counts[stage]==0),None)
        diagnostics.update(method='catalog_filter_stages_v1',counts=counts,
            reason_code=failure[0] if failure else 'matched',
            explanation=failure[1] if failure else 'Applicable candidates found; inspection and configuration verification remain required.',
            returned_count=min(len(result),20),truncated=len(result)>20,
            limitation='Stage counts are sequential filters of this local catalog only; no match does not prove parts do not exist elsewhere.')
    return result[:20]
