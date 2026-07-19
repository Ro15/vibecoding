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
