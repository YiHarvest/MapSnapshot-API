"""任务状态持久化、响应序列化和 HTTP 辅助函数。"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import Request
from fastapi.responses import JSONResponse

from server.core.config import (
    BASE_URL,
    DEFAULT_PORT,
    SNAPSHOT_DIR,
    TASK_MAX_AGE_SECONDS,
)

Task = dict[str, Any]


def send_json(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    """返回 JSON 响应。"""
    return JSONResponse(payload, status_code=status_code)


def get_origin(request: Request) -> str:
    """从请求头获取服务源地址。"""
    host = request.headers.get("host") or f"127.0.0.1:{DEFAULT_PORT}"
    protocol = request.headers.get("x-forwarded-proto") or "http"
    return f"{protocol}://{host}{BASE_URL}"


def generate_task_id() -> str:
    """生成唯一任务 ID。"""
    return uuid.uuid4().hex


def normalize_callback_url(callback_url: str | None) -> str:
    """规范化和验证回调 URL。"""
    if not callback_url:
        return ""
    try:
        parsed = urlparse(callback_url)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunparse(parsed)


def safe_task_path(task_id: str) -> Path | None:
    """构建安全的任务文件路径，防止路径遍历攻击。"""
    safe_task_id = Path(task_id).name
    if safe_task_id != task_id:
        return None
    return SNAPSHOT_DIR / f"{safe_task_id}.json"


def _load_task_file(result_path: Path) -> Task | None:
    if not result_path.exists():
        return None
    try:
        task = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return task if isinstance(task, dict) else None


async def load_task(task_id: str) -> Task | None:
    """从磁盘加载任务状态。"""
    result_path = safe_task_path(task_id)
    if result_path is None:
        return None
    return await asyncio.to_thread(_load_task_file, result_path)


def _write_task_file(result_path: Path, payload: str) -> None:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(payload, encoding="utf-8")


async def persist_task(task: Task) -> None:
    """持久化任务状态到磁盘。"""
    result_path = SNAPSHOT_DIR / f"{task['taskId']}.json"
    payload = json.dumps(task, ensure_ascii=False, indent=2)
    await asyncio.to_thread(
        _write_task_file,
        result_path,
        payload,
    )


def _remove_task_files(task_id: str) -> None:
    for extension in (".png", ".json"):
        try:
            (SNAPSHOT_DIR / f"{task_id}{extension}").unlink(missing_ok=True)
        except OSError:
            pass


async def cleanup_expired_tasks(tasks: dict[str, Task]) -> int:
    """清理过期任务及其关联文件。"""
    now_ms = int(datetime.now().timestamp() * 1000)
    cutoff_ms = now_ms - TASK_MAX_AGE_SECONDS * 1000
    expired_ids = [
        task_id
        for task_id, task in tasks.items()
        if task.get("createdAt", 0) < cutoff_ms
    ]
    for task_id in expired_ids:
        tasks.pop(task_id, None)
    await asyncio.gather(
        *(asyncio.to_thread(_remove_task_files, task_id) for task_id in expired_ids)
    )
    return len(expired_ids)


def _value_label(task: Task) -> str:
    """获取任务的值标签。"""
    return str(task.get("valueLabel") or "状态")


def _public_regions(task: Task, *, include_level: bool) -> list[dict[str, Any]]:
    """提取公开的区域列表。"""
    fields = (
        ("name", "adcode", "level", "value")
        if include_level
        else ("name", "adcode", "value")
    )
    return [
        {field: region[field] for field in fields} for region in task.get("regions", [])
    ]


def _public_districts(task: Task) -> list[dict[str, Any]]:
    """提取公开的区县列表。"""
    return [
        {
            "name": district["name"],
            "adcode": district["adcode"],
            "value": district["value"],
        }
        for district in task.get("districts", [])
    ]


def _callback_metadata(task: Task) -> dict[str, Any]:
    """构建回调元数据。"""
    return {
        "taskId": task["taskId"],
        "status": task["status"],
        "valueLabel": _value_label(task),
        "imageUrl": task.get("imageUrl", ""),
        "mapUrl": task.get("mapUrl", ""),
    }


def build_callback_payload(task: Task) -> Task:
    """构建回调响应体。"""
    result = _callback_metadata(task)
    task_type = task.get("taskType")
    if task_type == "city":
        result["city"] = {
            "name": task.get("city", {}).get("name", ""),
            "adcode": task.get("city", {}).get("adcode", ""),
        }
        result["districts"] = _public_districts(task)
        if task.get("failedDistricts"):
            result["failedDistricts"] = task["failedDistricts"]
    elif task_type == "province":
        result["province"] = {
            "name": task.get("province", {}).get("name", ""),
            "adcode": task.get("province", {}).get("adcode", ""),
        }
        result["regions"] = _public_regions(task, include_level=False)
        if task.get("failedRegions"):
            result["failedRegions"] = task["failedRegions"]
    else:
        result["regions"] = _public_regions(task, include_level=True)
        if task.get("failedRegions"):
            result["failedRegions"] = task["failedRegions"]
    return result


def serialize_public_task(task: Task) -> Task:
    """序列化任务为公开响应格式。"""
    status = task["status"]
    if status == "done":
        result = build_callback_payload(task)
    elif status == "failed":
        result = {
            "taskId": task["taskId"],
            "status": status,
            "valueLabel": _value_label(task),
            "message": task.get("message") or "任务失败",
        }
        task_type = task.get("taskType")
        if task_type == "city":
            result.update(
                {
                    "city": task.get("city", {}),
                    "districts": task.get("districts", []),
                    "failedDistricts": task.get("failedDistricts", []),
                }
            )
        elif task_type == "province":
            result.update(
                {
                    "province": task.get("province", {}),
                    "regions": task.get("regions", []),
                    "failedRegions": task.get("failedRegions", []),
                }
            )
        else:
            result.update(
                {
                    "regions": task.get("regions", []),
                    "failedRegions": task.get("failedRegions", []),
                }
            )
    else:
        result = {
            "taskId": task["taskId"],
            "status": status,
            "valueLabel": _value_label(task),
        }

    if task.get("callbackUrl"):
        result["callback"] = {
            "url": task["callbackUrl"],
            "error": task.get("callbackError"),
        }
    return result
