"""Pydantic schemas for MCP tool inputs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..models import Override


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OverrideToolInput(Override):
    """MCP override body; kill_switch requires confirm_kill_switch=true."""

    model_config = ConfigDict(extra="forbid")

    confirm_kill_switch: bool = Field(
        default=False,
        description="Required true when kill_switch is set.",
    )


class ConfigPatchInput(StrictModel):
    patch: dict = Field(description="Partial config deep-merge patch.")


class HistoryLimitInput(StrictModel):
    limit: int = Field(default=100, ge=1, le=1000)


class TelemetryWindowInput(StrictModel):
    hours: int = Field(default=24, ge=1, le=720)


class GridEventsInput(StrictModel):
    days: int = Field(default=7, ge=1, le=90)


class TraceSectionsInput(StrictModel):
    sections: str | None = Field(
        default=None,
        description="Comma-separated sections or 'all'. Default core forensics.",
    )


class AskInput(StrictModel):
    question: str = Field(max_length=2000)
