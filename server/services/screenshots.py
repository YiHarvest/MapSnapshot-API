"""Playwright 截图操作。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from server.core.config import (
    DEVICE_SCALE_FACTOR,
    MAP_READY_TIMEOUT_MS,
    SCREENSHOT_DELAY_MS,
    VIEWPORT,
)


async def capture_share_page(
    *,
    browser: Any,
    url: str,
    output_path: Path,
) -> None:
    """打开分享页面，等待地图加载完成后截图保存为 PNG。"""

    page = await browser.new_page(
        viewport=VIEWPORT,
        device_scale_factor=DEVICE_SCALE_FACTOR,
    )
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_function(
            "() => window.__MAP_READY__ === true",
            timeout=MAP_READY_TIMEOUT_MS,
        )
        await page.wait_for_timeout(SCREENSHOT_DELAY_MS)
        await page.screenshot(path=str(output_path), full_page=False)
    finally:
        await page.close()
