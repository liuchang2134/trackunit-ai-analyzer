from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform_asset_loader import load_platform_asset, UUID_PATTERN, EQUIPMENT_HINT_PATTERN

router = APIRouter(prefix='/assistant/platform-asset', tags=['Platform device import'])


class PlatformAssetLoadRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    equipment_id_hint: str | None = Field(default=None, pattern=EQUIPMENT_HINT_PATTERN, max_length=100)

    @field_validator('equipment_id_hint', mode='before')
    @classmethod
    def trim_hint(cls, value):
        return value.strip() if isinstance(value, str) else value


@router.post('/{asset_id}/load')
def load_current_asset(request: PlatformAssetLoadRequest | None = None, asset_id: str = Path(pattern=UUID_PATTERN)):
    try:
        result = load_platform_asset(asset_id, request.equipment_id_hint if request else None)
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})
    except OSError:
        raise HTTPException(503, '本地设备资料暂时无法保存，请稍后重试。') from None
