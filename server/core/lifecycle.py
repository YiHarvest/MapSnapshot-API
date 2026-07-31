"""FastAPI 生命周期管理，管理浏览器和清理资源。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from playwright.async_api import async_playwright

from server.core.config import (
    CLEANUP_INTERVAL_SECONDS,
    SCREENSHOT_CONCURRENCY,
    playwright_executable_path,
)
from server.core.runtime import RuntimeState
from server.services import cleanup_expired_tasks

logger = logging.getLogger(__name__)


async def _browser_executable() -> str | None:
    """获取浏览器可执行文件路径，优先使用环境变量配置。"""

    if playwright_executable_path and await asyncio.to_thread(
        Path(playwright_executable_path).exists
    ):
        return playwright_executable_path
    return None


async def _cleanup_loop(state: RuntimeState) -> None:
    """定期清理过期任务的后台循环。"""

    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        await cleanup_expired_tasks(state.tasks)


async def shutdown_runtime_resources(state: RuntimeState) -> None:
    """安全关闭浏览器和 Playwright 资源，处理已断开连接的情况。"""

    # 取消清理任务
    cleanup_task = state.cleanup_task
    state.cleanup_task = None
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

    # 获取并清空浏览器实例
    browser = state.browser_pool.get("browser")
    playwright = state.browser_pool.get("playwright")
    state.browser_pool.update({"playwright": None, "browser": None})

    # 关闭浏览器
    if browser:
        try:
            await browser.close()
        except Exception as exc:
            logger.warning("关闭时浏览器已不可用: %s", exc)

    # 停止 Playwright
    if playwright:
        try:
            await playwright.stop()
        except Exception as exc:
            logger.warning("关闭时 Playwright 已不可用: %s", exc)


def build_lifespan(state: RuntimeState):
    """创建绑定到指定运行时状态的生命周期管理器。"""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # 初始化截图并发信号量
        state.screenshot_semaphore = asyncio.Semaphore(SCREENSHOT_CONCURRENCY)
        # 启动后台清理任务
        state.cleanup_task = asyncio.create_task(_cleanup_loop(state))

        # 启动 Playwright
        playwright = await async_playwright().start()
        executable_path = await _browser_executable()

        # 启动浏览器
        try:
            launch_options: dict[str, object] = {"headless": True}
            if executable_path:
                launch_options.update(
                    {
                        "executable_path": executable_path,
                        "args": ["--disable-gpu"],
                    }
                )
            browser = await playwright.chromium.launch(**launch_options)
        except Exception:
            await playwright.stop()
            raise

        # 保存实例到运行时状态
        state.browser_pool.update({"playwright": playwright, "browser": browser})

        try:
            yield
        finally:
            # 应用关闭时清理资源
            await shutdown_runtime_resources(state)

    return lifespan
