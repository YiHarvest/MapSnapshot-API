"""路由模块共享的依赖容器。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request


@dataclass
class SnapshotContext:
    """截图任务执行上下文，封装路由处理器共享的依赖和回调。"""

    task_store: dict[str, dict[str, Any]]  # 内存中的任务状态存储
    browser_pool: dict[str, Any]  # Playwright 浏览器实例池
    get_screenshot_semaphore: Callable[[], asyncio.Semaphore | None]  # 截图并发信号量
    generate_task_id: Callable[[], str]  # 任务 ID 生成器
    get_origin: Callable[[Request], str]  # 从请求头获取服务源地址
    send_callback: Callable[[dict[str, Any], str], Awaitable[None]]  # HTTP 回调发送器
    infer_level: Callable[[str], str]  # 从 adcode 推断行政级别
    get_region_index: Callable[[], Awaitable[dict[str, dict[str, Any]]]]  # 获取区域索引
    resolve_regions: Callable[  # 解析请求中的区域列表
        [list[dict[str, Any]]],
        Awaitable[tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    ]
