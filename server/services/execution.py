"""后台任务并发和错误处理。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from server.core.config import SNAPSHOT_DIR, amap_key
from server.services.screenshots import capture_share_page
from server.services.tasks import persist_task

Task = dict[str, Any]


class ExecutionContext(Protocol):
    """截图任务执行上下文协议。"""

    task_store: dict[str, Task]  # 任务状态存储
    browser_pool: dict[str, Any]  # 浏览器实例池
    send_callback: Callable[[Task, str], Awaitable[None]]  # 回调发送函数

    def get_screenshot_semaphore(self):  # 截图并发信号量
        ...


async def send_callback_safely(
    *,
    task: Task,
    origin: str,
    callback: Callable[[Task, str], Awaitable[None]],
) -> None:
    """安全发送回调，记录错误但不影响截图结果。"""

    try:
        await callback(task, origin)
    except Exception as exc:
        task["callbackError"] = str(exc)


async def execute_snapshot_task(
    *,
    task_id: str,
    origin: str,
    context: ExecutionContext,
    prepare: Callable[[Task, ExecutionContext], Awaitable[bool]],
    map_key: str = amap_key,
    capture: Callable[..., Awaitable[None]] = capture_share_page,
    persist: Callable[[Task], Awaitable[None]] = persist_task,
    snapshot_dir: Path = SNAPSHOT_DIR,
) -> None:
    """执行各类地图任务共用的校验、截图、持久化和回调流程。"""

    task = context.task_store.get(task_id)
    if not task:
        return

    if not map_key:
        task.update(status="failed", message="missing VITE_AMAP_KEY")
    elif not await prepare(task, context):
        task.update(
            status="failed",
            message="some regions could not be resolved",
        )
    else:
        await asyncio.to_thread(snapshot_dir.mkdir, parents=True, exist_ok=True)
        file_name = f"{task_id}.png"
        try:
            await capture(
                browser=context.browser_pool["browser"],
                url=task["mapUrl"],
                output_path=snapshot_dir / file_name,
            )
            task.update(
                status="done",
                imageUrl=f"{origin}/api/v1/snapshots/{file_name}",
            )
        except Exception as exc:
            task.update(status="failed", message=str(exc) or "screenshot failed")

    await persist(task)
    await send_callback_safely(
        task=task,
        origin=origin,
        callback=context.send_callback,
    )


async def run_background_task(
    *,
    task_id: str,
    origin: str,
    context: ExecutionContext,
    runner: Callable[[str, str, Any], Awaitable[None]],
    persist: Callable[[Task], Awaitable[None]] = persist_task,
) -> None:
    """在共享信号量控制下运行任务，捕获异常并持久化失败状态。"""

    async def guarded_run() -> None:
        try:
            await runner(task_id, origin, context)
        except Exception as exc:
            task = context.task_store.get(task_id)
            if not task:
                return
            task["status"] = "failed"
            task["message"] = str(exc) or "task execution failed"
            await persist(task)

    semaphore = context.get_screenshot_semaphore()
    if semaphore is None:
        await guarded_run()
        return

    async with semaphore:
        await guarded_run()


def schedule_background_task(
    *,
    task_id: str,
    origin: str,
    context: ExecutionContext,
    runner: Callable[[str, str, Any], Awaitable[None]],
) -> asyncio.Task[None]:
    """调度受并发和失败保护的后台任务。"""

    return asyncio.create_task(
        run_background_task(
            task_id=task_id,
            origin=origin,
            context=context,
            runner=runner,
        )
    )


def schedule_snapshot_task(
    *,
    task_id: str,
    origin: str,
    context: ExecutionContext,
    prepare: Callable[[Task, ExecutionContext], Awaitable[bool]],
    execute: Callable[..., Awaitable[None]] = execute_snapshot_task,
) -> asyncio.Task[None]:
    """调度使用共享截图执行管线的后台任务。"""

    async def runner(
        current_task_id: str,
        current_origin: str,
        current_context: ExecutionContext,
    ) -> None:
        await execute(
            task_id=current_task_id,
            origin=current_origin,
            context=current_context,
            prepare=prepare,
        )

    return schedule_background_task(
        task_id=task_id,
        origin=origin,
        context=context,
        runner=runner,
    )
