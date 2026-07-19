"""Pydantic response models for Guardrail."""
from __future__ import annotations

from pydantic import BaseModel


class IngestResponse(BaseModel):
    source: str
    source_format: str
    resource_count: int
    parse_errors: list[dict]
    scan_id: int
    finding_count: int
    risk_score: int
    grade: str


class FindingOut(BaseModel):
    id: int
    scan_id: int
    address: str
    provider: str
    rtype: str
    policy: str
    title: str
    severity: str
    framework: str
    detail: str
    remediation: str
    source: str


class ScanOut(BaseModel):
    id: int
    ran_at: str
    source: str
    source_format: str
    resource_count: int
    finding_count: int
    risk_score: int
    grade: str
