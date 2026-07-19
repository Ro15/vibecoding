"""SQLite repository layer."""
from __future__ import annotations

import json
from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.orm import Base, Finding, IngestedFile, RawLine, Resource, Scan
from app.core.models import FindingResult, NormalizedResource

VALID_STATUSES = ("open", "dismissed", "remediated", "stale")


def init_db(path: str):
    engine = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope(engine):
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def record_file(session: Session, provider: str, filename: str, sha256: str):
    existing = session.scalar(select(IngestedFile).where(IngestedFile.sha256 == sha256))
    if existing:
        return existing, False
    f = IngestedFile(provider=provider, filename=filename, sha256=sha256)
    session.add(f)
    session.flush()
    return f, True


def stage_raw_lines(session: Session, file_id: int, payloads: list[dict]):
    session.add_all([RawLine(file_id=file_id, line_no=i, payload_json=json.dumps(p, default=str))
                     for i, p in enumerate(payloads, start=1)])


def upsert_resources(session: Session, resources: list[NormalizedResource]) -> int:
    count = 0
    for r in resources:
        row = session.scalar(select(Resource).where(
            Resource.provider == r.provider,
            Resource.resource_id == r.resource_id,
            Resource.billing_period == r.billing_period))
        if row is None:
            row = Resource(provider=r.provider, resource_id=r.resource_id,
                           resource_type=r.resource_type, region=r.region,
                           billing_period=r.billing_period, monthly_cost=r.monthly_cost,
                           usage_hours=r.usage_hours, state=r.state,
                           created_at=r.created_at, tags_json=json.dumps(r.tags))
            session.add(row)
        else:
            row.monthly_cost = r.monthly_cost
            row.usage_hours = r.usage_hours
            row.state = r.state
            row.resource_type = r.resource_type
            row.region = r.region
            row.created_at = r.created_at
            row.tags_json = json.dumps(r.tags)
        count += 1
    session.flush()
    return count


def list_resources(session: Session, provider: str | None = None) -> list[Resource]:
    q = select(Resource)
    if provider:
        q = q.where(Resource.provider == provider)
    return list(session.scalars(q))


def to_normalized(row: Resource) -> NormalizedResource:
    return NormalizedResource(
        provider=row.provider, resource_id=row.resource_id,
        resource_type=row.resource_type, region=row.region,
        billing_period=row.billing_period, monthly_cost=row.monthly_cost,
        usage_hours=row.usage_hours, state=row.state, created_at=row.created_at,
        tags=json.loads(row.tags_json or "{}"), raw_ref=row.id)


def create_scan(session: Session, resource_count: int) -> Scan:
    scan = Scan(resource_count=resource_count)
    session.add(scan)
    session.flush()
    return scan


def apply_findings(session: Session, scan: Scan, results: list[FindingResult]) -> dict:
    """Dedupe on (resource_id, rule); lifecycle: open/updated/stale, dismissed sticky."""
    stats = {"new": 0, "updated": 0, "stale": 0}
    seen_keys = set()
    for fr in results:
        key = (fr.resource.resource_id, fr.rule)
        seen_keys.add(key)
        row = session.scalar(select(Finding).where(
            Finding.resource_id == fr.resource.resource_id, Finding.rule == fr.rule))
        if row is None:
            session.add(Finding(
                provider=fr.resource.provider, resource_id=fr.resource.resource_id,
                resource_type=fr.resource.resource_type, region=fr.resource.region,
                rule=fr.rule, category=fr.category, severity=fr.severity,
                est_monthly_savings=fr.est_monthly_savings, reason=fr.reason,
                status="open", first_seen_scan_id=scan.id, last_seen_scan_id=scan.id))
            stats["new"] += 1
        else:
            row.est_monthly_savings = fr.est_monthly_savings
            row.severity = fr.severity
            row.reason = fr.reason
            row.last_seen_scan_id = scan.id
            if row.status == "stale":
                row.status = "open"  # reappeared
            stats["updated"] += 1

    for row in session.scalars(select(Finding).where(Finding.status.in_(("open",)))):
        if (row.resource_id, row.rule) not in seen_keys:
            row.status = "stale"
            stats["stale"] += 1

    session.flush()
    open_findings = list(session.scalars(select(Finding).where(Finding.status == "open")))
    scan.finding_count = len(open_findings)
    scan.total_savings = round(sum(f.est_monthly_savings for f in open_findings), 2)
    session.flush()
    return stats


def list_findings(session: Session, provider: str | None = None, rule: str | None = None,
                  status: str | None = None, min_savings: float | None = None) -> list[Finding]:
    q = select(Finding).order_by(Finding.est_monthly_savings.desc())
    if provider:
        q = q.where(Finding.provider == provider)
    if rule:
        q = q.where(Finding.rule == rule)
    if status:
        q = q.where(Finding.status == status)
    if min_savings is not None:
        q = q.where(Finding.est_monthly_savings >= min_savings)
    return list(session.scalars(q))


def get_finding(session: Session, finding_id: int) -> Finding:
    row = session.get(Finding, finding_id)
    if row is None:
        raise KeyError(f"finding {finding_id} not found")
    return row


def set_finding_status(session: Session, finding_id: int, status: str) -> Finding:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}; must be one of {VALID_STATUSES}")
    row = get_finding(session, finding_id)
    row.status = status
    session.flush()
    return row


def list_scans(session: Session) -> list[Scan]:
    return list(session.scalars(select(Scan).order_by(Scan.id)))
