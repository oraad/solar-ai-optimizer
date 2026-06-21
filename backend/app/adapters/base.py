"""The logical inverter interface the engine programs against.

The decision engine NEVER references Deye (or any vendor) specifics. It only
talks to this interface. A concrete adapter maps logical capabilities to a real
device (e.g. Home Assistant entities).
"""

from __future__ import annotations

import abc

from ..models import Capability, Telemetry


class InverterAdapter(abc.ABC):
    """Abstract capability model for a hybrid inverter + battery."""

    @abc.abstractmethod
    async def read_telemetry(self) -> Telemetry:
        """Return a fresh snapshot of all available read capabilities."""

    @abc.abstractmethod
    async def read_capability(self, capability: Capability) -> float | bool | None:
        """Read back the current value of a single write capability (for verify)."""

    @abc.abstractmethod
    def supports(self, capability: Capability) -> bool:
        """Whether this adapter has an entity mapped for the capability."""

    # --- Writes (logical) -------------------------------------------------- #
    @abc.abstractmethod
    async def set_grid_charge(self, enabled: bool) -> None:
        ...

    @abc.abstractmethod
    async def set_max_grid_charge_current(self, amps: float) -> None:
        ...

    async def apply(self, capability: Capability, value: float | bool) -> None:
        """Dispatch a write by logical capability."""
        if capability is Capability.GRID_CHARGE_ENABLE:
            await self.set_grid_charge(bool(value))
        elif capability is Capability.MAX_GRID_CHARGE_CURRENT:
            await self.set_max_grid_charge_current(float(value))
        else:  # pragma: no cover - defensive
            raise ValueError(f"Unknown capability: {capability}")
