"""Configuration: environment settings (.env) + YAML config (entity map, specs).

Two layers:
- `Settings` reads secrets/runtime flags from environment (.env).
- `AppConfig` reads the structured YAML (capability map, battery, reserve, ...).
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ForecastProvider = Literal["open-meteo", "solcast"]

DEFAULT_HEARTBEAT_ENTITY = "input_datetime.solar_optimizer_heartbeat"
class Settings(BaseSettings):
    """Process settings sourced from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ha_base_url: str = Field(default="http://homeassistant.local:8123")
    ha_token: str = Field(default="")
    ha_verify_ssl: bool = Field(default=True)

    config_path: str = Field(default="config/config.yaml")
    # Writable directory for runtime state (config overrides, learned model).
    data_dir: str = Field(default="./data")
    database_url: str = Field(default="sqlite+aiosqlite:///./data/solar.db")

    shadow_mode: bool = Field(default=True)
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="text")

    # When served behind a reverse proxy / HA ingress, the URL path prefix.
    root_path: str = Field(default="")

    # Home Assistant Supervisor add-on integration (auto-populated when running
    # as an add-on: SUPERVISOR_TOKEN is injected and the core API is reachable
    # at http://supervisor/core).
    supervisor_token: str = Field(default="", alias="SUPERVISOR_TOKEN")

    # Optional Solcast
    solcast_api_key: str = Field(default="")
    solcast_resource_id: str = Field(default="")

    # Optional ML load forecasting (Phase 4)
    ml_load_enabled: bool = Field(default=False)

    # Optional LLM
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1")
    llm_enabled: bool = Field(default=False)

    # Optional bearer token for mutating API calls in standalone deployments.
    api_token: str = Field(default="")

    # Comma-separated CORS origins; "*" allows all (default for local dev).
    cors_origins: str = Field(default="*")

    @property
    def is_addon(self) -> bool:
        return bool(self.supervisor_token)

    @model_validator(mode="after")
    def _wire_supervisor(self) -> "Settings":
        """When running as an HA add-on, talk to the core via the Supervisor.

        Note: HA ingress strips its path prefix before proxying to the add-on,
        so the app is served at "/" internally and needs no root_path. The
        frontend uses relative URLs to stay ingress-compatible.
        """
        if self.supervisor_token and not self.ha_token:
            self.ha_base_url = "http://supervisor/core"
            self.ha_token = self.supervisor_token
        return self


# --------------------------------------------------------------------------- #
# YAML config models
# --------------------------------------------------------------------------- #
class InverterReadMap(BaseModel):
    pv_power: str | None = None
    load_power: str | None = None
    battery_soc: str | None = None
    battery_power: str | None = None
    grid_power: str | None = None
    grid_present: str | None = None
    battery_temp: str | None = None


class InverterWriteMap(BaseModel):
    grid_charge_enable: str | None = None
    max_grid_charge_current: str | None = None
    work_mode: str | None = None


class InverterConfig(BaseModel):
    read: InverterReadMap = Field(default_factory=InverterReadMap)
    write: InverterWriteMap = Field(default_factory=InverterWriteMap)
    invert_battery_power: bool = False
    work_modes: dict[str, str] = Field(default_factory=dict)


class BatteryConfig(BaseModel):
    capacity_kwh: float = 10.0
    max_charge_a: float = 100.0
    max_grid_charge_a: float = 60.0
    nominal_voltage: float = 51.2
    min_soc_floor: float = 20.0
    max_soc_ceiling: float = 100.0
    round_trip_efficiency: float = 0.9

    @property
    def usable_wh_per_soc(self) -> float:
        """Watt-hours represented by 1% of state-of-charge."""
        return self.capacity_kwh * 1000.0 / 100.0


class ReserveConfig(BaseModel):
    critical_load_w: float = 400.0
    min_autonomy_hours: float = 12.0
    solar_bridge_buffer_pct: float = 15.0
    cloudy_extra_buffer_pct: float = 15.0


class PvArray(BaseModel):
    name: str = "array"
    kwp: float = 5.0
    tilt: float = 15.0
    azimuth: float = 180.0


class TemperatureConfig(BaseModel):
    """Outdoor-temperature driven load modeling (heaters/coolers).

    Temperature is the primary seasonal driver via heating/cooling degree-hours;
    calendar month is a coarse fallback when no temperature is available.
    """

    enabled: bool = True
    # Optional HA outdoor-temperature sensor for actuals + bias correction.
    ha_entity: str | None = None
    hdd_base_c: float = 18.0          # heating degrees accrue below this
    cdd_base_c: float = 24.0          # cooling degrees accrue above this
    use_month_fallback: bool = True
    # Resilience floor: a mild forecast may not shrink expected load below this
    # fraction of the (dow, hour) baseline.
    min_load_fraction: float = 0.8
    # History window used for the temperature regression and month factors.
    training_days: int = 45


class ForecastConfig(BaseModel):
    provider: ForecastProvider = "open-meteo"
    latitude: float = 0.0
    longitude: float = 0.0
    timezone: str = "auto"
    arrays: list[PvArray] = Field(default_factory=lambda: [PvArray()])
    temperature: TemperatureConfig = Field(default_factory=TemperatureConfig)

    @field_validator("provider", mode="before")
    @classmethod
    def _normalize_provider(cls, v: object) -> str:
        if v is None:
            return "open-meteo"
        s = str(v).strip().lower()
        if s not in ("open-meteo", "solcast"):
            raise ValueError("forecast.provider must be 'open-meteo' or 'solcast'")
        return s

    @property
    def location_configured(self) -> bool:
        return not (self.latitude == 0.0 and self.longitude == 0.0)


class ControlConfig(BaseModel):
    loop_interval_seconds: int = 30
    forecast_interval_minutes: int = 30
    min_write_interval_seconds: int = 60
    enforce_hard_bounds: bool = True
    ha_stale_after_seconds: int = 120


class FailSafeConfig(BaseModel):
    """Heartbeat + shutdown fail-safe (grid charge at max when optimizer stops)."""

    heartbeat_entity: str | None = DEFAULT_HEARTBEAT_ENTITY
    heartbeat_enabled: bool = True
    shutdown_failsafe_enabled: bool = True


class LoadTier(BaseModel):
    """A sheddable load tier mapped to one or more HA switches.

    Hysteresis: shed when SOC drops below `shed_below_soc`, restore when SOC
    rises above `restore_above_soc`. Lower-priority tiers shed first.
    All entities in a tier shed and restore together.
    """

    name: str
    switches: list[str] = Field(default_factory=list)
    shed_below_soc: float = 40.0
    restore_above_soc: float = 55.0
    priority: int = 0                 # higher = more important (shed last)

    @model_validator(mode="before")
    @classmethod
    def _normalize_switches(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "switch" in d:
            legacy = d.pop("switch")
            if "switches" not in d and legacy:
                d["switches"] = [legacy] if isinstance(legacy, str) else list(legacy)
        return d

    def entity_ids(self) -> list[str]:
        return [s.strip() for s in self.switches if s and s.strip()]

    @model_validator(mode="after")
    def _hysteresis_order(self) -> "LoadTier":
        if self.restore_above_soc <= self.shed_below_soc:
            raise ValueError(
                f"load_shedding tier '{self.name}': restore_above_soc "
                f"({self.restore_above_soc}) must be > shed_below_soc "
                f"({self.shed_below_soc})"
            )
        return self


class LoadSheddingConfig(BaseModel):
    enabled: bool = False
    # When the grid is physically present, keep all tiers powered.
    restore_all_when_grid_present: bool = True
    tiers: list[LoadTier] = Field(default_factory=list)


class EngineConfig(BaseModel):
    mode: str = "rules"
    mpc_horizon_hours: int = 48

    @field_validator("mode")
    @classmethod
    def _valid_mode(cls, v: str) -> str:
        if v not in {"rules", "mpc"}:
            raise ValueError("engine.mode must be 'rules' or 'mpc'")
        return v


class HaConfig(BaseModel):
    """Home Assistant connection, editable from the UI and persisted.

    When base_url + token are set here they take precedence over environment
    variables, so the app can run with no .env file. Leave empty to fall back to
    the environment / Supervisor (add-on) credentials.
    """

    base_url: str = ""
    token: str = ""
    verify_ssl: bool = True


class AppConfig(BaseModel):
    """Top-level structured config (UI-editable, persisted to the data dir)."""

    model_config = ConfigDict(extra="ignore")

    ha: HaConfig = Field(default_factory=HaConfig)
    inverter: InverterConfig = Field(default_factory=InverterConfig)
    battery: BatteryConfig = Field(default_factory=BatteryConfig)
    reserve: ReserveConfig = Field(default_factory=ReserveConfig)
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)
    control: ControlConfig = Field(default_factory=ControlConfig)
    fail_safe: FailSafeConfig = Field(default_factory=FailSafeConfig)
    engine: EngineConfig = Field(default_factory=EngineConfig)
    load_shedding: LoadSheddingConfig = Field(default_factory=LoadSheddingConfig)


def load_app_config(path: str | Path) -> AppConfig:
    """Load and validate the YAML config file. Falls back to defaults if absent."""
    p = Path(path)
    if not p.exists():
        return AppConfig()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data)


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
