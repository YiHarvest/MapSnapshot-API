import asyncio
from pathlib import Path

from server.core.config import (
    DEVICE_SCALE_FACTOR,
    MAP_READY_TIMEOUT_MS,
    SCREENSHOT_DELAY_MS,
    VIEWPORT,
)
from server.services.screenshots import capture_share_page


class FakePage:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.closed = False

    async def goto(self, url: str, *, wait_until: str) -> None:
        self.calls.append(("goto", url, wait_until))

    async def wait_for_function(self, expression: str, *, timeout: int) -> None:
        self.calls.append(("wait_for_function", expression, timeout))

    async def wait_for_timeout(self, timeout: int) -> None:
        self.calls.append(("wait_for_timeout", timeout))

    async def screenshot(self, *, path: str, full_page: bool) -> None:
        self.calls.append(("screenshot", path, full_page))

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.options: dict[str, object] = {}

    async def new_page(self, **options: object) -> FakePage:
        self.options = options
        return self.page


def test_capture_share_page_uses_consistent_browser_settings(tmp_path: Path) -> None:
    page = FakePage()
    browser = FakeBrowser(page)
    output_path = tmp_path / "snapshot.png"

    asyncio.run(
        capture_share_page(
            browser=browser,
            url="http://example.test/share",
            output_path=output_path,
        )
    )

    assert browser.options == {
        "viewport": VIEWPORT,
        "device_scale_factor": DEVICE_SCALE_FACTOR,
    }
    assert page.calls == [
        ("goto", "http://example.test/share", "domcontentloaded"),
        (
            "wait_for_function",
            "() => window.__MAP_READY__ === true",
            MAP_READY_TIMEOUT_MS,
        ),
        ("wait_for_timeout", SCREENSHOT_DELAY_MS),
        ("screenshot", str(output_path), False),
    ]
    assert page.closed is True
