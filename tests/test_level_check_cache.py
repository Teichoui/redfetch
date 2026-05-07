import asyncio
import importlib
from unittest.mock import AsyncMock, patch

from redfetch import config

class _FakeMainScreen:
    def __init__(self) -> None:
        self.ding_visible = None
        self.welcome = None
        self.account = None

    def show_ding_button(self, visible: bool) -> None:
        self.ding_visible = visible

    def update_welcome_label(self, text: str) -> None:
        self.welcome = text

    def update_account_label(self, text: str) -> None:
        self.account = text


class _FakeApp:
    def __init__(self) -> None:
        self.username = None
        self._main_screen = _FakeMainScreen()

    def _get_main_screen(self):
        return self._main_screen


def test_load_user_level_forces_refresh(monkeypatch):
    monkeypatch.setattr(config, "settings", type("_Settings", (), {"ENV": "LIVE"})(), raising=False)
    Redfetch = importlib.import_module("redfetch.terminal_ui").Redfetch

    app = _FakeApp()
    kiss_mock = AsyncMock(return_value=True)

    with patch("redfetch.terminal_ui.auth.get_username", new=AsyncMock(return_value="Teichoui")), \
         patch("redfetch.terminal_ui.auth.get_api_headers", new=AsyncMock(return_value={"Authorization": "Bearer token"})), \
         patch("redfetch.terminal_ui.api.is_kiss_downloadable", new=kiss_mock):
        asyncio.run(Redfetch.load_user_level.__wrapped__(app))

    kiss_mock.assert_awaited_once_with({"Authorization": "Bearer token"}, force_refresh=True)
    assert app.username == "Teichoui"
    assert app._main_screen.ding_visible is False
    assert "level 2" in app._main_screen.account
