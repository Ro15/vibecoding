"""Guarded remediation execution.

The executor is pluggable; the default SimulatedExecutor never touches a cloud
account — it echoes what WOULD run, preserving the tool's generate-only safety
guarantee while exercising the full approval + audit pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.models import RemediationPlan


@dataclass
class ExecutionResult:
    dry_run: bool
    commands: list[str]
    output: str
    succeeded: bool


class SimulatedExecutor:
    """Echoes commands instead of running them. No cloud credentials, no side effects."""

    name = "simulated"

    def execute(self, plan: RemediationPlan, dry_run: bool) -> ExecutionResult:
        commands = [step.cli for step in plan.steps]
        lines = []
        for step in plan.steps:
            prefix = "[dry-run]" if dry_run else "[simulated]"
            kind = "DESTRUCTIVE" if step.destructive else "verify"
            lines.append(f"{prefix} ({kind}) would execute: {step.cli}")
        lines.append(f"{'[dry-run]' if dry_run else '[simulated]'} plan for "
                     f"{plan.resource_id} completed with 0 errors.")
        return ExecutionResult(dry_run=dry_run, commands=commands,
                               output="\n".join(lines), succeeded=True)


DEFAULT_EXECUTOR = SimulatedExecutor()
