"""Watchdog ORM models (SQLite). Stores buckets (not raw events) + anomalies + alerts."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Ingest(Base):
    __tablename__ = "ingests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String(255), default="")
    source_format: Mapped[str] = mapped_column(String(32), default="")
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    bucket_seconds: Mapped[int] = mapped_column(Integer, default=60)


class Bucket(Base):
    __tablename__ = "buckets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingest_id: Mapped[int] = mapped_column(ForeignKey("ingests.id"))
    service: Mapped[str] = mapped_column(String(128))
    bucket_start: Mapped[datetime] = mapped_column(DateTime)
    total: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)


class AnomalyRow(Base):
    __tablename__ = "anomalies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingest_id: Mapped[int] = mapped_column(ForeignKey("ingests.id"))
    service: Mapped[str] = mapped_column(String(128))
    bucket_start: Mapped[datetime] = mapped_column(DateTime)
    error_count: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(8))


class AlertRow(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingest_id: Mapped[int] = mapped_column(ForeignKey("ingests.id"))
    service: Mapped[str] = mapped_column(String(128))
    bucket_start: Mapped[datetime] = mapped_column(DateTime)
    error_count: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(8))
    payload_json: Mapped[str] = mapped_column(Text)
    delivered: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Config(Base):
    __tablename__ = "config"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))
