"""Executor shed snapshot and restore behavior."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import BatteryConfig, ControlConfig, LoadTier
from app.control.executor import Executor
from app.i18n.skip_keys import SKIP_ALREADY_SET, SKIP_WAS_OFF_BEFORE_SHED
from app.models import ShedAction
from app.shed_snapshots import EntitySnapshot, ShedSnapshotStore
from tests.conftest import DUMMY_MSG


def _executor(ha: MagicMock, store: ShedSnapshotStore) -> Executor:
    adapter = MagicMock()
    adapter.supports = MagicMock(return_value=False)
    return Executor(
        adapter,
        ha,
        BatteryConfig(),
        ControlConfig(),
        snapshot_store=store,
    )


@asynccontextmanager
async def _mock_repo():
    with patch("app.control.executor.repo.save_shed_execution", new_callable=AsyncMock):
        yield


def test_restore_skips_when_was_off(tmp_path):
    store = ShedSnapshotStore(str(tmp_path))
    store.capture("switch.pool", was_on=False)
    ha = MagicMock()
    ha.is_stale = MagicMock(return_value=False)
    ex = _executor(ha, store)
    tiers = [LoadTier(name="pool", switches=["switch.pool"])]

    async def run():
        async with _mock_repo():
            return await ex.apply_shed_actions(
                [
                    ShedAction(
                        tier="pool",
                        entity="switch.pool",
                        desired_on=True,
                        reason=DUMMY_MSG,
                    )
                ],
                shadow_mode=False,
                tiers=tiers,
            )

    res = asyncio.run(run())
    assert res[0].skipped_reason == SKIP_WAS_OFF_BEFORE_SHED
    ha.toggle_entity.assert_not_called()


def test_shed_captures_snapshot_when_already_off(tmp_path):
    store = ShedSnapshotStore(str(tmp_path))
    ha = MagicMock()
    ha.is_stale = MagicMock(return_value=False)
    ha.get_state = AsyncMock(return_value={"entity_id": "switch.pool", "state": "off"})
    ha.toggle_entity = AsyncMock()
    ex = _executor(ha, store)
    tiers = [
        LoadTier(
            name="pool",
            switches=["switch.pool"],
            state_entities={"switch.pool": []},
        )
    ]

    async def run():
        async with _mock_repo():
            return await ex.apply_shed_actions(
                [
                    ShedAction(
                        tier="pool",
                        entity="switch.pool",
                        desired_on=False,
                        reason=DUMMY_MSG,
                    )
                ],
                shadow_mode=False,
                tiers=tiers,
            )

    res = asyncio.run(run())
    assert res[0].skipped_reason == SKIP_ALREADY_SET
    snap = store.get("switch.pool")
    assert snap is not None
    assert snap.was_on is False


def test_shadow_mode_no_snapshot(tmp_path):
    store = ShedSnapshotStore(str(tmp_path))
    ha = MagicMock()
    ha.is_stale = MagicMock(return_value=False)
    ex = _executor(ha, store)
    tiers = [LoadTier(name="pool", switches=["switch.pool"])]

    async def run():
        async with _mock_repo():
            await ex.apply_shed_actions(
                [
                    ShedAction(
                        tier="pool",
                        entity="switch.pool",
                        desired_on=False,
                        reason=DUMMY_MSG,
                    )
                ],
                shadow_mode=True,
                tiers=tiers,
            )

    asyncio.run(run())
    assert store.get("switch.pool") is None


def test_restore_companions_when_power_already_on(tmp_path):
    store = ShedSnapshotStore(str(tmp_path))
    store.capture(
        "switch.pool",
        was_on=True,
        companions={
            "select.mode": EntitySnapshot(state="auto", attributes={}),
        },
    )
    ha = MagicMock()
    ha.is_stale = MagicMock(return_value=False)
    ha.get_state = AsyncMock(return_value={"entity_id": "switch.pool", "state": "on"})
    ha.toggle_entity = AsyncMock()
    ha.select_option = AsyncMock()
    ex = _executor(ha, store)
    tiers = [
        LoadTier(
            name="pool",
            switches=["switch.pool"],
            state_entities={"switch.pool": ["select.mode"]},
        )
    ]

    async def run():
        async with _mock_repo():
            return await ex.apply_shed_actions(
                [
                    ShedAction(
                        tier="pool",
                        entity="switch.pool",
                        desired_on=True,
                        reason=DUMMY_MSG,
                    )
                ],
                shadow_mode=False,
                tiers=tiers,
            )

    res = asyncio.run(run())
    ha.toggle_entity.assert_not_called()
    ha.select_option.assert_awaited_once()
    assert res[0].companions_restored == ["select.mode"]
