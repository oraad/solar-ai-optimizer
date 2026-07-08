"""HA add-on pre-release update polling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.ha_addon_update import (
    _pick_newest_release,
    ha_addon_update_cycle,
)


def test_pick_newest_release_prefers_stable_over_beta():
    releases = [
        {"tag_name": "v0.6.10-beta.2"},
        {"tag_name": "v0.6.10"},
    ]
    assert _pick_newest_release(releases, "0.6.10-beta.1") == "0.6.10"


@pytest.mark.asyncio
async def test_ha_addon_update_skips_when_option_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings(
        SUPERVISOR_TOKEN="token",
        ADDON_PRERELEASE_UPDATES=False,
    )
    with patch(
        "app.services.ha_addon_update._fetch_releases",
        new_callable=AsyncMock,
    ) as mock_fetch:
        await ha_addon_update_cycle(settings)
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_ha_addon_update_notifies_without_supervisor_post(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = Settings(
        SUPERVISOR_TOKEN="token",
        ADDON_PRERELEASE_UPDATES=True,
    )
    releases = [{"tag_name": "v9.9.9"}]
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_client = AsyncMock()
    mock_client.get.return_value = MagicMock(
        raise_for_status=MagicMock(),
        json=MagicMock(return_value={"data": {"slug": "repo_solar_ai_optimizer"}}),
    )
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with (
        patch("app.services.ha_addon_update.__version__", "0.5.0"),
        patch(
            "app.services.ha_addon_update._fetch_releases",
            new_callable=AsyncMock,
            return_value=(releases, False),
        ),
        patch("app.services.ha_addon_update.httpx.AsyncClient", return_value=mock_client),
    ):
        await ha_addon_update_cycle(settings)

    assert mock_client.post.called
    state_file = tmp_path / ".ha_prerelease_update.json"
    assert state_file.is_file()
    assert "9.9.9" in state_file.read_text(encoding="utf-8")
