from typing import Literal, Optional

from pydantic import BaseModel


class Machine(BaseModel):
    machine_id: str
    trackunit_asset_id: Optional[str] = None
    equipment_id: Optional[str] = None
    serial_number: str
    model: str
    machine_type: str
    customer: str
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    last_seen_at: str


class TelemetrySnapshot(BaseModel):
    machine_id: str
    trackunit_asset_id: Optional[str] = None
    equipment_id: Optional[str] = None
    operating_hours: Optional[float] = None
    idle_hours: Optional[float] = None
    fuel_remaining_percent: Optional[float] = None
    engine_status: Optional[Literal["running", "stopped", "unknown"]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    recorded_at: str
    raw_payload: Optional[dict] = None


class FaultCode(BaseModel):
    machine_id: str
    trackunit_asset_id: Optional[str] = None
    equipment_id: Optional[str] = None
    spn: Optional[int] = None
    fmi: Optional[int] = None
    fault_code: str
    description: str
    severity: Literal["low", "medium", "high", "critical"]
    occurred_at: str
    status: Literal["open", "resolved", "acknowledged"]
    raw_payload: Optional[dict] = None


class MachineAnalysisPrompt(BaseModel):
    machine_id: str
    prompt: str


class FleetAnalysisPrompt(BaseModel):
    prompt: str
