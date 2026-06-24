"""Configuration: environment settings (.env) + YAML config (entity map, specs).

Two layers:
- `Settings` reads secrets/runtime flags from environment (.env).
- `AppConfig` reads the structured YAML (capability map, battery, reserve, ...).
"""

from __future__ import annotations

import functools
from pathlib import Path
from enum import Enum
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

    # Ingress / authorization
    trust_ingress_headers: bool = Field(default=False)
    admin_user_ids: str = Field(default="")
    admin_cache_ttl_seconds: int = Field(default=300)

    local_admin_username: str = Field(default="admin")
    local_admin_password: str = Field(default="")
    local_admin_password_hash: str = Field(default="")

    session_secret: str = Field(default="")
    session_ttl_hours: int = Field(default=24)
    session_cookie_secure: bool = Field(default=False)

    # Documentation / screenshot mode only — injects synthetic telemetry.
    demo_mode: bool = Field(default=False)

    # Opt-in self-update from the dashboard (requires Docker socket mount).
    self_update_enabled: bool = Field(default=False)
    self_update_image: str = Field(
        default="ghcr.io/oraad/solar-ai-optimizer:latest"
    )
    self_update_container: str = Field(default="solar-optimizer")
    self_update_env_file: str = Field(default="")
    self_update_data_volume: str = Field(default="solar-data")
    self_update_data_path: str = Field(default="/app/data")
    self_update_port: int = Field(default=8000)

    @property
    def is_addon(self) -> bool:
        return bool(self.supervisor_token)

    @property
    def ingress_trusted(self) -> bool:
        return self.is_addon or self.trust_ingress_headers

    @property
    def local_auth_enabled(self) -> bool:
        return bool(self.local_admin_password or self.local_admin_password_hash)

    @property
    def admin_user_id_set(self) -> frozenset[str]:
        return frozenset(
            u.strip() for u in self.admin_user_ids.split(",") if u.strip()
        )

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
        if self.is_addon:
            self.trust_ingress_headers = True
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


class InverterConfig(BaseModel):
    read: InverterReadMap = Field(default_factory=InverterReadMap)
    write: InverterWriteMap = Field(default_factory=InverterWriteMap)
    invert_battery_power: bool = False


class BatteryConfig(BaseModel):
    capacity_kwh: float = 10.0
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
    restore_enabled: bool = True      # SOC-based restore when soc >= restore_above_soc
    restore_on_grid: bool = True      # restore when grid present (if global flag on)
    state_entities: dict[str, list[str]] = Field(default_factory=dict)

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

    def companions_for(self, entity_id: str) -> list[str] | None:
        """Return companion entity IDs, None to autodiscover, [] for switch-only."""
        if entity_id not in self.state_entities:
            return None
        return list(self.state_entities.get(entity_id) or [])

    @model_validator(mode="after")
    def _hysteresis_order(self) -> "LoadTier":
        if self.restore_above_soc <= self.shed_below_soc:
            raise ValueError(
                f"load_shedding tier '{self.name}': restore_above_soc "
                f"({self.restore_above_soc}) must be > shed_below_soc "
                f"({self.shed_below_soc})"
            )
        known = set(self.entity_ids())
        cleaned: dict[str, list[str]] = {}
        for key, companions in self.state_entities.items():
            k = key.strip()
            if not k or k not in known:
                continue
            cleaned[k] = [c.strip() for c in companions if c and str(c).strip()]
        object.__setattr__(self, "state_entities", cleaned)
        return self


class LoadSheddingConfig(BaseModel):
    enabled: bool = False
    # When the grid is physically present, keep all tiers powered.
    restore_all_when_grid_present: bool = True
    tiers: list[LoadTier] = Field(default_factory=list)


class GridChargeFactor(str, Enum):
    soc_gap = "soc_gap"
    remaining_solar_today = "remaining_solar_today"
    next_solar_power = "next_solar_power"
    load_power = "load_power"
    battery_power = "battery_power"
    grid_window = "grid_window"
    blackout_risk = "blackout_risk"
    solar_bridge = "solar_bridge"


_DEFAULT_FACTOR_ORDER = [
    GridChargeFactor.soc_gap,
    GridChargeFactor.grid_window,
    GridChargeFactor.battery_power,
    GridChargeFactor.remaining_solar_today,
    GridChargeFactor.next_solar_power,
    GridChargeFactor.load_power,
    GridChargeFactor.solar_bridge,
    GridChargeFactor.blackout_risk,
]


class GridChargeConfig(BaseModel):
    ramp_enabled: bool = True
    factor_order: list[GridChargeFactor] = Field(
        default_factory=lambda: list(_DEFAULT_FACTOR_ORDER)
    )
    min_grid_charge_a: float = 5.0
    ramp_step_a: float = 10.0
    off_threshold_a: float = 1.0
    next_solar_horizon_hours: int = 6

    @field_validator("factor_order", mode="before")
    @classmethod
    def _normalize_factor_order(cls, v: object) -> list[GridChargeFactor]:
        if not v:
            return list(_DEFAULT_FACTOR_ORDER)
        seen: set[GridChargeFactor] = set()
        out: list[GridChargeFactor] = []
        for item in v:
            try:
                factor = GridChargeFactor(str(item))
            except ValueError:
                continue
            if factor not in seen:
                seen.add(factor)
                out.append(factor)
        return out or list(_DEFAULT_FACTOR_ORDER)


class OptimizationPriority(str, Enum):
    resilience = "resilience"
    savings = "savings"
    self_sufficiency = "self_sufficiency"


_DEFAULT_PRIORITY_ORDER = [
    OptimizationPriority.resilience,
    OptimizationPriority.savings,
    OptimizationPriority.self_sufficiency,
]


class EngineConfig(BaseModel):
    mode: str = "rules"
    mpc_horizon_hours: int = 48
    priority_order: list[OptimizationPriority] = Field(
        default_factory=lambda: list(_DEFAULT_PRIORITY_ORDER)
    )

    @field_validator("mode")
    @classmethod
    def _valid_mode(cls, v: str) -> str:
        if v not in {"rules", "mpc"}:
            raise ValueError("engine.mode must be 'rules' or 'mpc'")
        return v

    @field_validator("priority_order", mode="before")
    @classmethod
    def _normalize_priority_order(cls, v: object) -> list[OptimizationPriority]:
        if not v:
            return list(_DEFAULT_PRIORITY_ORDER)
        out: list[OptimizationPriority] = []
        seen: set[str] = set()
        for item in v:
            if isinstance(item, OptimizationPriority):
                priority = item
                key = item.value
            else:
                try:
                    priority = OptimizationPriority(str(item))
                except ValueError:
                    continue
                key = priority.value
            if key in seen:
                continue
            seen.add(key)
            out.append(priority)
        if len(out) != len(_DEFAULT_PRIORITY_ORDER):
            raise ValueError(
                "engine.priority_order must list each of "
                "resilience, savings, self_sufficiency exactly once"
            )
        return out


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
    grid_charge: GridChargeConfig = Field(default_factory=GridChargeConfig)


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
