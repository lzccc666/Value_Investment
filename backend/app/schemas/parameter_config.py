from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ParameterConfigPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_sampling: dict[str, object]
    financial_flags: dict[str, object]
    analyst_engine: dict[str, object]
    valuation_rule_matrix: dict[str, object]
    memo_decision: dict[str, object]
    valuation_models: dict[str, object]
    price_decision: dict[str, object]


class ParameterConfigUpdateRequest(BaseModel):
    config_json: ParameterConfigPayload
    warnings_acknowledged: bool = False


class ParameterValidationIssue(BaseModel):
    path: str
    message: str
    severity: Literal["error", "warning"]
    code: str


class ParameterValidationResult(BaseModel):
    valid: bool
    errors: list[ParameterValidationIssue] = Field(default_factory=list)
    warnings: list[ParameterValidationIssue] = Field(default_factory=list)
    actual_parameter_count: int = 0
    audit_parameter_count: int = 0


class ParameterMetadataItem(BaseModel):
    path: str
    domain: str
    label: str
    code_name: str
    description: str
    unit: str
    default_value: object
    current_value: object
    minimum: float | None = None
    maximum: float | None = None
    editable: bool = True
    expert: bool = False
    audit_only: bool = False
    risk: Literal["low", "medium", "high"] = "medium"


class ParameterConfigCurrentResponse(BaseModel):
    config_json: dict[str, object]
    config_hash: str
    source: Literal["source_file", "builtin_default", "builtin_fallback"]
    fallback_reason: str | None = None
    validation: ParameterValidationResult
    metadata: list[ParameterMetadataItem]


class ParameterConfigPublishResponse(BaseModel):
    config_json: dict[str, object]
    config_hash: str
    source: Literal["source_file"]
    validation: ParameterValidationResult
    metadata: list[ParameterMetadataItem]
