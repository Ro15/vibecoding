"""Guardrail ORM models (SQLite)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String(255), default="")
    source_format: Mapped[str] = mapped_column(String(32), default="")
    resource_count: Mapped[int] = mapped_column(Integer, default=0)
    finding_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    grade: Mapped[str] = mapped_column(String(2), default="A+")


class FindingRow(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"))
    address: Mapped[str] = mapped_column(String(512))
    provider: Mapped[str] = mapped_column(String(16))
    rtype: Mapped[str] = mapped_column(String(32))
    policy: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(8))
    framework: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text)
    remediation: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(255), default="")
