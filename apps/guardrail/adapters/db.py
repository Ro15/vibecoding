"""Guardrail SQLite repository, built on common.db."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.guardrail.adapters.orm import Base, FindingRow, Scan
from apps.guardrail.core.models import Finding
from apps.guardrail.core.scoring import grade, risk_score
from common.db import init_engine, session_scope  # noqa: F401  (re-exported)

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def init_db(path: str):
    return init_engine(path, Base.metadata)


def record_scan(session: Session, source: str, source_format: str,
                resource_count: int, findings: list[Finding]) -> Scan:
    score = risk_score(findings)
    scan = Scan(source=source, source_format=source_format,
                resource_count=resource_count, finding_count=len(findings),
                risk_score=score, grade=grade(score))
    session.add(scan)
    session.flush()
    for f in findings:
        session.add(FindingRow(
            scan_id=scan.id, address=f.resource.address, provider=f.resource.provider,
            rtype=f.resource.rtype, policy=f.policy, title=f.title, severity=f.severity,
            framework=f.framework, detail=f.detail, remediation=f.remediation,
            source=f.resource.source))
    session.flush()
    return scan


def latest_scan(session: Session) -> Scan | None:
    return session.scalar(select(Scan).order_by(Scan.id.desc()).limit(1))


def list_scans(session: Session) -> list[Scan]:
    return list(session.scalars(select(Scan).order_by(Scan.id)))


def list_findings(session: Session, scan_id: int | None = None, severity: str | None = None,
                  framework: str | None = None, rtype: str | None = None) -> list[FindingRow]:
    if scan_id is None:
        latest = latest_scan(session)
        if latest is None:
            return []
        scan_id = latest.id
    q = select(FindingRow).where(FindingRow.scan_id == scan_id)
    if severity:
        q = q.where(FindingRow.severity == severity)
    if framework:
        q = q.where(FindingRow.framework == framework)
    if rtype:
        q = q.where(FindingRow.rtype == rtype)
    rows = list(session.scalars(q))
    rows.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    return rows


def get_finding(session: Session, finding_id: int) -> FindingRow:
    row = session.get(FindingRow, finding_id)
    if row is None:
        raise KeyError(f"finding {finding_id} not found")
    return row
