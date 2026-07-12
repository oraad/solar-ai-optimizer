"""Executor shed snapshot and restore behavior."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import BatteryConfig, ControlConfig, LoadTier
from app.control.executor import Executor
from app.i18n.skip_keys import (
    SKIP_ALREADY_SET,
    SKIP_HA_STALE,
    SKIP_NO_SHED_SNAPSHOT,
    SKIP_WAS_OFF_BEFORE_SHED,
)
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


def test_episode_capture_once_preserves_snapshot_for_restore(tmp_path):
    """Repeat shed while off must not overwrite was_on=True before restore."""
    store = ShedSnapshotStore(str(tmp_path))
    ha = MagicMock()
    ha.is_stale = MagicMock(return_value=False)
    ha.toggle_entity = AsyncMock()
    ha.select_option = AsyncMock()
    ha.get_state = AsyncMock(
        side_effect=[
            # First shed: power on + companion capture
            {"entity_id": "switch.pool", "state": "on"},
            {"entity_id": "select.mode", "state": "auto", "attributes": {}},
            {"entity_id": "switch.pool", "state": "on"},
            {"entity_id": "switch.pool", "state": "off"},  # verify after toggle
            # Second shed: already off — preserve pending snapshot
            {"entity_id": "switch.pool", "state": "off"},
            # Restore: power still off, then verify on
            {"entity_id": "switch.pool", "state": "off"},
            {"entity_id": "switch.pool", "state": "on"},
        ]
    )
    ex = _executor(ha, store)
    # Avoid verify delay sleeps in this multi-step test.
    ex._verify_delay = 0
    tiers = [
        LoadTier(
            name="pool",
            switches=["switch.pool"],
            state_entities={"switch.pool": ["select.mode"]},
        )
    ]
    shed = ShedAction(
        tier="pool",
        entity="switch.pool",
        desired_on=False,
        reason=DUMMY_MSG,
    )
    restore = ShedAction(
        tier="pool",
        entity="switch.pool",
        desired_on=True,
        reason=DUMMY_MSG,
    )

    async def run():
        async with _mock_repo():
            first = await ex.apply_shed_actions([shed], shadow_mode=False, tiers=tiers)
            snap = store.get("switch.pool")
            assert snap is not None
            assert snap.was_on is True
            assert "select.mode" in snap.companions

            second = await ex.apply_shed_actions([shed], shadow_mode=False, tiers=tiers)
            snap2 = store.get("switch.pool")
            assert snap2 is not None
            assert snap2.was_on is True
            assert "select.mode" in snap2.companions

            restored = await ex.apply_shed_actions(
                [restore], shadow_mode=False, tiers=tiers
            )
            return first, second, restored

    first, second, restored = asyncio.run(run())
    assert first[0].applied is True
    assert "select.mode" in first[0].companions_captured
    assert second[0].skipped_reason == SKIP_ALREADY_SET
    assert second[0].companions_captured == ["select.mode"]
    assert restored[0].applied is True
    assert restored[0].companions_restored == ["select.mode"]
    assert store.get("switch.pool") is None
    ha.toggle_entity.assert_any_await("switch.pool", False)
    ha.toggle_entity.assert_any_await("switch.pool", True)
    ha.select_option.assert_awaited()


def test_shed_skips_snapshot_when_ha_state_unavailable(tmp_path):
    store = ShedSnapshotStore(str(tmp_path))
    ha = MagicMock()
    ha.is_stale = MagicMock(return_value=False)
    ha.get_state = AsyncMock(return_value=None)
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
    assert store.get("switch.pool") is None
    # Power write may still proceed with current=None; snapshot must stay empty.
    assert res[0].companions_captured == []


def test_no_shed_snapshot_skip_not_persisted(tmp_path):
    store = ShedSnapshotStore(str(tmp_path))
    ha = MagicMock()
    ha.is_stale = MagicMock(return_value=False)
    ex = _executor(ha, store)
    tiers = [LoadTier(name="pool", switches=["switch.pool"])]
    save = AsyncMock()

    async def run():
        with patch("app.control.executor.repo.save_shed_execution", new=save):
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
    assert res[0].skipped_reason == SKIP_NO_SHED_SNAPSHOT
    save.assert_not_awaited()


def test_already_set_shed_skip_not_persisted(tmp_path):
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
    save = AsyncMock()

    async def run():
        with patch("app.control.executor.repo.save_shed_execution", new=save):
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
    save.assert_not_awaited()


def test_stale_shed_captures_snapshot_before_write_gate(tmp_path):
    store = ShedSnapshotStore(str(tmp_path))
    ha = MagicMock()
    # Sticky stale so successful get_state does not clear the write gate in tests.
    ha.is_stale = MagicMock(return_value=True)
    ha.get_state = AsyncMock(
        side_effect=[
            {"entity_id": "switch.pool", "state": "on"},
            {"entity_id": "select.mode", "state": "auto", "attributes": {}},
        ]
    )
    ha.toggle_entity = AsyncMock()
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
                        desired_on=False,
                        reason=DUMMY_MSG,
                    )
                ],
                shadow_mode=False,
                tiers=tiers,
            )

    res = asyncio.run(run())
    assert res[0].skipped_reason == SKIP_HA_STALE
    ha.toggle_entity.assert_not_called()
    snap = store.get("switch.pool")
    assert snap is not None
    assert snap.was_on is True
    assert "select.mode" in snap.companions
    assert res[0].companions_captured == ["select.mode"]


def test_stale_shed_no_snapshot_when_state_unavailable(tmp_path):
    store = ShedSnapshotStore(str(tmp_path))
    ha = MagicMock()
    ha.is_stale = MagicMock(return_value=True)
    ha.get_state = AsyncMock(return_value=None)
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
    assert res[0].skipped_reason == SKIP_HA_STALE
    assert store.get("switch.pool") is None
    ha.toggle_entity.assert_not_called()


def test_stale_capture_then_fresh_shed_preserves_and_applies(tmp_path):
    store = ShedSnapshotStore(str(tmp_path))
    ha = MagicMock()
    ha.is_stale = MagicMock(side_effect=[True, False])
    ha.toggle_entity = AsyncMock()
    ha.get_state = AsyncMock(
        side_effect=[
            # Stale cycle: capture while on
            {"entity_id": "switch.pool", "state": "on"},
            # Fresh cycle: preserve pending (no capture read), then current + verify
            {"entity_id": "switch.pool", "state": "on"},
            {"entity_id": "switch.pool", "state": "off"},
        ]
    )
    ex = _executor(ha, store)
    ex._verify_delay = 0
    tiers = [
        LoadTier(
            name="pool",
            switches=["switch.pool"],
            state_entities={"switch.pool": []},
        )
    ]
    shed = ShedAction(
        tier="pool",
        entity="switch.pool",
        desired_on=False,
        reason=DUMMY_MSG,
    )

    async def run():
        async with _mock_repo():
            first = await ex.apply_shed_actions([shed], shadow_mode=False, tiers=tiers)
            snap = store.get("switch.pool")
            assert snap is not None
            assert snap.was_on is True
            second = await ex.apply_shed_actions([shed], shadow_mode=False, tiers=tiers)
            return first, second

    first, second = asyncio.run(run())
    assert first[0].skipped_reason == SKIP_HA_STALE
    assert second[0].applied is True
    assert store.get("switch.pool") is not None
    assert store.get("switch.pool").was_on is True
    ha.toggle_entity.assert_awaited_once_with("switch.pool", False)


def test_ha_stale_shed_skip_not_persisted(tmp_path):
    store = ShedSnapshotStore(str(tmp_path))
    ha = MagicMock()
    ha.is_stale = MagicMock(return_value=True)
    ha.get_state = AsyncMock(return_value={"entity_id": "switch.pool", "state": "on"})
    ha.toggle_entity = AsyncMock()
    ex = _executor(ha, store)
    tiers = [
        LoadTier(
            name="pool",
            switches=["switch.pool"],
            state_entities={"switch.pool": []},
        )
    ]
    save = AsyncMock()

    async def run():
        with patch("app.control.executor.repo.save_shed_execution", new=save):
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
    assert res[0].skipped_reason == SKIP_HA_STALE
    save.assert_not_awaited()
