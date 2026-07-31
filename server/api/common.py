"""地图截图路由共享逻辑。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any, Protocol

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from server.services.execution import schedule_snapshot_task
from server.services.naming import choose_display_name, normalize_text
from server.services.tasks import load_task
from server.services.templates import render_share_template

Task = dict[str, Any]
RegionIndex = dict[str, dict[str, dict[str, Any]]]


class RouteContext(Protocol):
    task_store: dict[str, Task]

    def generate_task_id(self) -> str: ...

    def infer_level(self, adcode: str) -> str: ...

    async def get_region_index(self) -> RegionIndex: ...


def create_snapshot_task(
    context: RouteContext,
    origin: str,
    *,
    task_type: str,
    share_path: str,
    value_label: str,
    callback_url: str,
    data: Mapping[str, Any],
) -> Task:
    """创建含公共元数据的截图任务并写入内存。"""

    task_id = context.generate_task_id()
    task: Task = {
        "taskId": task_id,
        "taskType": task_type,
        "status": "processing",
        "valueLabel": value_label,
        "callbackUrl": callback_url,
        "imageUrl": "",
        "mapUrl": f"{origin}/api/v1/{share_path}?taskId={task_id}",
        "createdAt": int(datetime.now().timestamp() * 1000),
        **data,
    }
    context.task_store[task_id] = task
    return task


def task_created_response(task: Task) -> dict[str, Any]:
    """返回统一任务创建响应。"""

    return {
        "success": True,
        "data": {
            "taskId": task["taskId"],
            "status": task["status"],
            "valueLabel": task["valueLabel"],
        },
    }


def submit_snapshot_task(
    context: RouteContext,
    origin: str,
    *,
    task_type: str,
    share_path: str,
    value_label: str,
    callback_url: str,
    data: Mapping[str, Any],
    prepare: Callable[[Task, Any], Awaitable[bool]],
    schedule: Callable[..., Any] = schedule_snapshot_task,
) -> dict[str, Any]:
    """创建、调度并返回统一任务响应。"""

    task = create_snapshot_task(
        context,
        origin,
        task_type=task_type,
        share_path=share_path,
        value_label=value_label,
        callback_url=callback_url,
        data=data,
    )
    schedule(
        task_id=task["taskId"],
        origin=origin,
        context=context,
        prepare=prepare,
    )
    return task_created_response(task)


async def render_share_page(
    template_name: str,
    task: Task,
    *region_keys: str,
    render: Callable[[str, dict[str, Any]], Awaitable[str]] = render_share_template,
) -> str:
    """渲染各类分享页共用上下文。"""

    return await render(
        template_name,
        {
            "taskId": task["taskId"],
            "valueLabel": task.get("valueLabel") or "状态",
            **{key: task[key] for key in region_keys},
        },
    )


async def get_share_task(
    task_id: str,
    context: RouteContext,
    *,
    prepare: Callable[[Task, RouteContext], Awaitable[bool]],
    load: Callable[[str], Awaitable[Task | None]] = load_task,
) -> Task:
    """读取内存或持久化任务；无效任务统一返回 404。"""

    task = context.task_store.get(task_id)
    if task is not None:
        return task

    task = await load(task_id)
    if task is None or not await prepare(task, context):
        raise HTTPException(status_code=404, detail="task not found")
    return task


async def share_page_response(
    task_id: str,
    context: RouteContext,
    *,
    prepare: Callable[[Task, RouteContext], Awaitable[bool]],
    template_name: str,
    region_keys: tuple[str, ...],
    render: Callable[[str, dict[str, Any]], Awaitable[str]] = render_share_template,
) -> HTMLResponse:
    """读取任务并返回统一分享页响应。"""

    task = await get_share_task(task_id, context, prepare=prepare)
    return HTMLResponse(
        await render_share_page(
            template_name,
            task,
            *region_keys,
            render=render,
        )
    )


async def resolve_index_region(
    requested: dict[str, str],
    context: RouteContext,
    *,
    missing_reason: str,
    level: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """按 adcode 解析单个行政区。"""

    index = await context.get_region_index()
    adcode = requested["adcode"]
    match = index["byAdcode"].get(adcode)
    if not match:
        return None, [
            {
                "name": requested["name"] or adcode,
                "reason": missing_reason,
            }
        ]

    return (
        {
            "name": choose_display_name(requested["name"], match.get("name"), adcode),
            "adcode": adcode,
            "level": level or context.infer_level(adcode),
            "center": match.get("center"),
        },
        [],
    )


async def resolve_index_regions(
    requested_regions: list[dict[str, str]],
    context: RouteContext,
    *,
    missing_reason: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """按 adcode 批量解析行政区。"""

    index = await context.get_region_index()
    resolved: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for region in requested_regions:
        adcode = region["adcode"]
        match = index["byAdcode"].get(adcode)
        if not match:
            failed.append(
                {
                    "name": region["name"] or adcode,
                    "reason": missing_reason,
                }
            )
            continue
        resolved.append(
            {
                "name": choose_display_name(
                    region["name"],
                    match.get("name"),
                    adcode,
                ),
                "adcode": adcode,
                "level": context.infer_level(adcode),
                "value": region["value"],
                "center": match.get("center"),
            }
        )
    return resolved, failed


def enrich_region_record(
    region: dict[str, Any],
    index: RegionIndex,
    infer_level: Callable[[str], str],
    *,
    level: str | None = None,
) -> bool:
    """用索引补全单个持久化行政区。"""

    adcode = normalize_text(region.get("adcode"))
    if not adcode:
        return False
    match = index["byAdcode"].get(adcode)
    if not match:
        return False
    region.update(
        name=choose_display_name(region.get("name"), match.get("name"), adcode),
        level=region.get("level") or level or infer_level(adcode),
        center=region.get("center") or match.get("center"),
    )
    return True


async def enrich_scope(
    task: Task,
    context: RouteContext,
    *,
    parent_key: str | None,
    children_key: str,
    parent_level: str | None = None,
) -> None:
    """补全范围任务中的父区域和子区域。"""

    index = await context.get_region_index()
    if parent_key:
        parent = task.get(parent_key)
        if isinstance(parent, dict):
            enrich_region_record(
                parent,
                index,
                context.infer_level,
                level=parent_level,
            )

    for child in task.get(children_key, []):
        if isinstance(child, dict):
            enrich_region_record(child, index, context.infer_level)
