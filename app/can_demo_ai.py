"""AI teaching demo on independently generated synthetic values ONLY.

This module deliberately does not import recorded_replay or accept telemetry,
free-form observations, file paths, vehicle identifiers or arbitrary prompts.
"""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.can_replay import synthetic_evidence
from app.deepseek_client import generate_structured_with_deepseek, get_deepseek_model


class SyntheticAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario: Literal['synthetic']
    at: int = Field(ge=0, le=480, strict=True)


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    component: str = Field(min_length=1, max_length=100)
    reasoning: str = Field(min_length=1, max_length=600)
    evidence_ids: list[str] = Field(min_length=1, max_length=7)
    inspection: str = Field(min_length=1, max_length=600)
    search_terms: list[str] = Field(min_length=1, max_length=4)


class Analysis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=1, max_length=1000)
    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=4)
    missing_evidence: list[str] = Field(min_length=1, max_length=6)


def analyze_synthetic(request: SyntheticAnalysisRequest):
    evidence = synthetic_evidence(request.at)
    messages = [
        {'role': 'system', 'content': (
            '你是工程机械排查助手。本次只有独立生成的装载机教学数据，没有真实车辆、故障码、维修手册或备件图册。'
            '用中文对时间窗口内的趋势做有条件的假设，最多三个部件方向；不能确诊、给预测概率、发明厂家阈值或订购料号。'
            '必须区分数据支持的现象和待核验的原因，每个假设引用给定 S1-S7 证据。'
            '检查顺序先确认测量、再外观检查、再由专业人员按维修手册检测；高温冷却系统不可打开加注盖。'
            'search_terms 只给部件名称或英文同义词，供日后在同 VIN XGSS 图册中人工核对。'
            '明确哪些故障因素无法由当前信号排除，不要把相关性说成因果。')},
        {'role': 'user', 'content': json.dumps(evidence, ensure_ascii=False)},
    ]
    report = Analysis.model_validate_json(generate_structured_with_deepseek(messages, Analysis.model_json_schema(), timeout_seconds=60))
    allowed = {row['id'] for row in evidence['evidence']}
    if any(not set(item.evidence_ids) <= allowed for item in report.hypotheses):
        raise ValueError('AI 返回了不存在的证据编号，请重试。')
    return {'report': report.model_dump(), 'input': evidence, 'provider': 'DeepSeek', 'model': get_deepseek_model(),
            'source_kind': 'synthetic', 'catalog_status': 'awaiting_same_vin_verification'}
