"""FastAPI 应用运行时状态。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeState:
    """路由处理器和后台任务共享的资源状态。"""

    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)  # 任务状态存储
    browser_pool: dict[str, Any] = field(  # Playwright 浏览器实例池
        default_factory=lambda: {"playwright": None, "browser": None}
    )
    region_index: dict[str, dict[str, Any]] | None = None  # 行政区划索引
    region_index_lock: asyncio.Lock | None = None  # 索引构建锁
    screenshot_semaphore: asyncio.Semaphore | None = None  # 截图并发信号量
    cleanup_task: asyncio.Task[None] | None = None  # 清理任务

    def get_screenshot_semaphore(self) -> asyncio.Semaphore | None:
        """获取截图并发信号量。"""
        return self.screenshot_semaphore
