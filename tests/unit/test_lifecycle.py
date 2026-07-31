import asyncio

from server.core import lifecycle
from server.core.lifecycle import shutdown_runtime_resources
from server.core.runtime import RuntimeState


class ClosedTransportBrowser:
    async def close(self) -> None:
        raise RuntimeError("handler is closed")


class PlaywrightHandle:
    def __init__(self) -> None:
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


def test_browser_executable_has_no_hard_coded_fallback(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle, "playwright_executable_path", "")
    monkeypatch.setattr(lifecycle.Path, "exists", lambda _path: True)

    assert asyncio.run(lifecycle._browser_executable()) is None


def test_shutdown_continues_when_browser_transport_is_already_closed() -> None:
    playwright = PlaywrightHandle()
    state = RuntimeState(
        browser_pool={
            "browser": ClosedTransportBrowser(),
            "playwright": playwright,
        }
    )

    asyncio.run(shutdown_runtime_resources(state))

    assert playwright.stopped is True
    assert state.browser_pool == {"playwright": None, "browser": None}
