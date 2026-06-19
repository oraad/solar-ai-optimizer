"""SQLAlchemy ORM table definitions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TelemetryRow(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    pv_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_soc: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    grid_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    grid_present: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    battery_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    outdoor_temp: Mapped[float | None] = mapped_column(Float, nullable=True)


class GridEventRow(Base):
    __tablename__ = "grid_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    grid_present: Mapped[bool] = mapped_column(Boolean)


class DecisionRow(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    target_soc: Mapped[float] = mapped_column(Float)
    blackout_risk: Mapped[str] = mapped_column(String(16))
    blackout_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    shadow_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    reserve_rationale: Mapped[str] = mapped_column(Text, default="")
    # JSON-encoded lists for audit.
    actions_json: Mapped[str] = mapped_column(Text, default="[]")
    shed_actions_json: Mapped[str] = mapped_column(Text, default="[]")


class ExecutionRow(Base):
    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    capability: Mapped[str] = mapped_column(String(48))
    requested: Mapped[str] = mapped_column(String(64))
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    skipped_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ShedExecutionRow(Base):
    __tablename__ = "shed_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    tier: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(128))
    desired_on: Mapped[bool] = mapped_column(Boolean)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    skipped_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
