"""Core domain models. Pure Python — no framework imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

RESOURCE_TYPES = ("disk", "vm", "ip", "snapshot", "other")


@dataclass
class NormalizedResource:
    provider: str
    resource_id: str
    resource_type: str
    region: str
    billing_period: str  # YYYY-MM
    monthly_cost: float
    usage_hours: float
    state: str  # attached|available|unattached|stopped|running|associated|unassociated|unknown
    created_at: date | None = None
    tags: dict = field(default_factory=dict)
    raw_ref: int | None = None


@dataclass
class FindingResult:
    resource: NormalizedResource
    rule: str
    category: str
    severity: str
    est_monthly_savings: float
    reason: str


@dataclass
class RemStep:
    order: int
    intent: str
    cli: str
    sdk_code: str
    destructive: bool


@dataclass
class RemediationPlan:
    rule: str
    provider: str
    resource_id: str
    steps: list[RemStep] = field(default_factory=list)
