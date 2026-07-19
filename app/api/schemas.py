"""Pydantic response models."""
from __future__ import annotations

from pydantic import BaseModel


class IngestResponse(BaseModel):
    provider: str
    filename: str
    duplicate: bool
    rows_ok: int
    rows_failed: int
    row_errors: list[dict]
    resources_upserted: int


class AnalyzeResponse(BaseModel):
    scan_id: int
    resource_count: int
    findings_new: int
    findings_updated: int
    findings_stale: int
    open_findings: int
    total_est_monthly_savings: float


class FindingOut(BaseModel):
    id: int
    provider: str
    resource_id: str
    resource_type: str
    region: str
    rule: str
    category: str
    severity: str
    est_monthly_savings: float
    reason: str
    status: str
    owner: str = ""
    remediated_at: str | None = None
    realized_monthly_savings: float = 0.0

    @classmethod
    def model_validate(cls, obj, **kwargs):  # coerce date -> isoformat string
        if kwargs.get("from_attributes") and getattr(obj, "remediated_at", None) is not None:
            data = {f: getattr(obj, f) for f in cls.model_fields if hasattr(obj, f)}
            data["remediated_at"] = obj.remediated_at.isoformat()
            return cls(**data)
        return super().model_validate(obj, **kwargs)


class ExecuteRequest(BaseModel):
    dry_run: bool = True
    approve: bool = False


class ExecutionOut(BaseModel):
    id: int
    finding_id: int
    actor: str
    executor: str
    dry_run: bool
    commands: list[str]
    output: str
    succeeded: bool
    executed_at: str


class SchedulePut(BaseModel):
    enabled: bool
    interval_minutes: int = 60
    webhook_url: str | None = None


class StatusPatch(BaseModel):
    status: str


class RemStepOut(BaseModel):
    order: int
    intent: str
    cli: str
    sdk_code: str
    destructive: bool


class RemediationOut(BaseModel):
    finding_id: int
    rule: str
    provider: str
    resource_id: str
    steps: list[RemStepOut]


class ScanOut(BaseModel):
    id: int
    ran_at: str
    resource_count: int
    finding_count: int
    total_savings: float
