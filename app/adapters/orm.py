"""SQLAlchemy ORM models (SQLite)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (Date, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class IngestedFile(Base):
    __tablename__ = "ingested_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RawLine(Base):
    __tablename__ = "raw_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("ingested_files.id"))
    line_no: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[str] = mapped_column(Text)


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (UniqueConstraint("provider", "resource_id", "billing_period"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    resource_id: Mapped[str] = mapped_column(String(512))
    resource_type: Mapped[str] = mapped_column(String(16))
    region: Mapped[str] = mapped_column(String(64))
    billing_period: Mapped[str] = mapped_column(String(7))
    monthly_cost: Mapped[float] = mapped_column(Float)
    usage_hours: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="{}")


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resource_count: Mapped[int] = mapped_column(Integer, default=0)
    finding_count: Mapped[int] = mapped_column(Integer, default=0)
    total_savings: Mapped[float] = mapped_column(Float, default=0.0)


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("resource_id", "rule"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    resource_id: Mapped[str] = mapped_column(String(512))
    resource_type: Mapped[str] = mapped_column(String(16))
    region: Mapped[str] = mapped_column(String(64))
    rule: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(8))
    est_monthly_savings: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    first_seen_scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id"), nullable=True)
    last_seen_scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id"), nullable=True)
