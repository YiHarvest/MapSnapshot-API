"""全国地图截图接口实现。

这个模块负责全国地图任务的请求校验、页面渲染、截图任务执行、
结果持久化和回调复用。用于在全国范围内展示多个区域标记。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, List

from fastapi import APIRouter, Body, Depends, Request as FastAPIRequest
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field, field_validator

try:
    from server.config import (
        DEVICE_SCALE_FACTOR,
        ERROR_MSG,
        MAP_COMPLETE_DELAY_MS,
        MAP_READY_FALLBACK_TIMEOUT_MS,
        MAP_READY_TIMEOUT_MS,
        MULTI_FITVIEW_PADDING,
        SCREENSHOT_DELAY_MS,
        SHARE_MAP_ZOOM,
        SHARE_MAP_ZOOMS,
        SHARE_POLYGON_STYLE,
        SINGLE_FITVIEW_PADDING,
        SINGLE_REGION_DEFAULT_ZOOM,
        SINGLE_REGION_ZOOM,
        SNAPSHOT_DIR,
        VIEWPORT,
        amap_key,
        amap_security_code,
    )
except ImportError:
    from config import (  # type: ignore
        DEVICE_SCALE_FACTOR,
        ERROR_MSG,
        MAP_COMPLETE_DELAY_MS,
        MAP_READY_FALLBACK_TIMEOUT_MS,
        MAP_READY_TIMEOUT_MS,
        MULTI_FITVIEW_PADDING,
        SCREENSHOT_DELAY_MS,
        SHARE_MAP_ZOOM,
        SHARE_MAP_ZOOMS,
        SHARE_POLYGON_STYLE,
        SINGLE_FITVIEW_PADDING,
        SINGLE_REGION_DEFAULT_ZOOM,
        SINGLE_REGION_ZOOM,
        SNAPSHOT_DIR,
        VIEWPORT,
        amap_key,
        amap_security_code,
    )


@dataclass
class NationSnapshotContext:
    """全国截图接口运行时依赖集合。

    由 `server.app` 注入，避免这个模块反向依赖主入口。
    """

    task_store: dict[str, dict[str, Any]]
    browser_pool: dict[str, Any]
    get_screenshot_semaphore: Callable[[], Optional[asyncio.Semaphore]]
    generate_task_id: Callable[[], str]
    get_origin: Callable[[FastAPIRequest], str]
    normalize_callback_url: Callable[[str | None], str]
    send_json: Callable[[dict[str, Any], int], Any]
    send_callback: Callable[[dict[str, Any], str], Awaitable[None]]
    serialize_task: Callable[[dict[str, Any]], dict[str, Any]]
    get_region_index: Callable[[], Awaitable[dict[str, dict[str, Any]]]]
    resolve_regions: Callable[
        [list[dict[str, Any]]],
        Awaitable[tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    ]


class NationShareQuery(BaseModel):
    """全国地图渲染页查询参数。"""

    taskId: str


class NationRegions(BaseModel):
    """全国地图截图的区域请求模型。"""

    name: str = Field(default="", description="选填，区域的展示名称")
    adcode: str = Field(..., description="必填，区域的行政区划编码")
    value: str = Field(default="", description="选填，该地区标注在气泡中的内容")


class NationSnapshotCreateRequest(BaseModel):
    """全国地图截图任务创建请求模型。"""

    regions: List[NationRegions] = Field(
        ..., min_length=1, description="区域列表，每个区域可设置独立的 value"
    )
    value_label: str = Field(
        default="状态", description="选填，页面中 value 前展示的标签。"
    )
    callback_url: str = Field(default="", description="任务完成后的回调地址（可选）")

    @field_validator("value_label", "callback_url", mode="before")
    @classmethod
    def normalize_string_fields(cls, value: Any) -> str:
        return str(value or "").strip()


NationShareQuery.model_rebuild()
NationRegions.model_rebuild()
NationSnapshotCreateRequest.model_rebuild()


_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_JINJA_ENV = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=True)


def _error(ctx: NationSnapshotContext, message: str, status_code: int = 400):
    """返回统一的错误 JSON。"""

    return ctx.send_json({"success": False, "message": message}, status_code)


def _render_national_share_page(task: dict[str, Any]) -> str:
    """渲染全国地图页面 HTML。"""

    escaped_security_code = json.dumps(amap_security_code, ensure_ascii=False)

    template = _JINJA_ENV.get_template("map_share.html")
    return template.render(
        security_config_js=(
            f"window._AMapSecurityConfig = {escaped_security_code}"
            f" ? {{ securityJsCode: {escaped_security_code} }} : undefined;"
        ),
        amap_key=amap_key,
        task_data={
            "taskId": task["taskId"],
            "regions": task["regions"],
            "valueLabel": task.get("valueLabel") or "状态",
        },
        share_poly_style=SHARE_POLYGON_STYLE,
        share_map_zoom=SHARE_MAP_ZOOM,
        share_map_zooms_0=SHARE_MAP_ZOOMS[0],
        share_map_zooms_1=SHARE_MAP_ZOOMS[1],
        single_region_zoom=SINGLE_REGION_ZOOM,
        single_region_default_zoom=SINGLE_REGION_DEFAULT_ZOOM,
        single_fitview_padding=", ".join(str(v) for v in SINGLE_FITVIEW_PADDING),
        multi_fitview_padding=", ".join(str(v) for v in MULTI_FITVIEW_PADDING),
        map_complete_delay_ms=MAP_COMPLETE_DELAY_MS,
        map_ready_fallback_timeout_ms=MAP_READY_FALLBACK_TIMEOUT_MS,
    )


def _serialize_national_task(task: dict[str, Any]) -> dict[str, Any]:
    """把全国任务序列化成持久化 JSON。"""

    result = {
        "taskId": task["taskId"],
        "taskType": "national",
        "status": task["status"],
        "valueLabel": task.get("valueLabel") or "状态",
        "imageUrl": task.get("imageUrl", ""),
        "mapUrl": task.get("mapUrl", ""),
        "regions": [
            {
                "name": region["name"],
                "adcode": region["adcode"],
                "level": region["level"],
                "value": region["value"],
            }
            for region in task.get("regions", [])
        ],
    }

    if task.get("failedRegions"):
        result["failedRegions"] = task["failedRegions"]
    if task.get("callbackUrl"):
        result["callback"] = {
            "url": task["callbackUrl"],
            "error": task.get("callbackError"),
        }

    return result


async def _load_persisted_national_task(
    task_id: str, ctx: NationSnapshotContext
) -> dict[str, Any] | None:
    """从磁盘恢复全国任务。

    这样服务重启后，之前生成的 map-share 链接仍然可打开。
    """

    safe_task_id = Path(task_id).name
    if safe_task_id != task_id:
        return None

    result_path = SNAPSHOT_DIR / f"{safe_task_id}.json"
    if not result_path.exists():
        return None

    try:
        task = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    regions = task.get("regions")
    if not isinstance(regions, list):
        return None

    index = await ctx.get_region_index()
    enriched_regions: list[dict[str, Any]] = []
    for region in regions:
        if not isinstance(region, dict):
            continue
        adcode = str(region.get("adcode") or "").strip()
        if not adcode:
            continue
        match = index["byAdcode"].get(adcode)
        name = str(region.get("name") or "").strip()
        if match and (not name or name == adcode or "?" in name or "\ufffd" in name):
            name = str(match.get("name") or "").strip() or adcode
        elif not name:
            name = adcode

        enriched_regions.append(
            {
                "name": name,
                "adcode": adcode,
                "level": str(
                    region.get("level")
                    or (match.get("level") if match else "")
                    or adcode[:2] + "0000"
                    if adcode.endswith("00")
                    else (
                        adcode[:4] + "00" if not adcode.endswith("0000") else "province"
                    )
                ),
                "value": str(region.get("value", "")).strip(),
                "center": region.get("center")
                or (match.get("center") if match else None),
            }
        )

    task["regions"] = enriched_regions
    return task


async def _run_national_task(
    task_id: str, origin: str, ctx: NationSnapshotContext
) -> None:
    """执行全国截图任务的主流程。"""

    task = ctx.task_store.get(task_id)
    if not task:
        return

    if not amap_key:
        task["status"] = "failed"
        task["message"] = ERROR_MSG["MISSING_AMAP_KEY"]
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
        result_json_path.write_text(
            json.dumps(_serialize_national_task(task), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await _send_callback_safely(task, origin, ctx)
        return

    resolved, failed_regions = await ctx.resolve_regions(task["requestedRegions"])
    task["regions"] = resolved
    task["failedRegions"] = failed_regions

    if failed_regions or not resolved:
        task["status"] = "failed"
        task["message"] = ERROR_MSG["REGIONS_NOT_FOUND"]
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
        result_json_path.write_text(
            json.dumps(_serialize_national_task(task), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await _send_callback_safely(task, origin, ctx)
        return

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page = None

    try:
        browser = ctx.browser_pool["browser"]
        page = await browser.new_page(
            viewport=VIEWPORT,
            device_scale_factor=DEVICE_SCALE_FACTOR,
        )
        await page.goto(task["mapUrl"], wait_until="domcontentloaded")
        await page.wait_for_function(
            "() => window.__MAP_READY__ === true",
            timeout=MAP_READY_TIMEOUT_MS,
        )
        await page.wait_for_timeout(SCREENSHOT_DELAY_MS)

        file_name = f"{task_id}.png"
        file_path = SNAPSHOT_DIR / file_name
        await page.screenshot(path=str(file_path), full_page=False)

        task["imageUrl"] = f"{origin}/api/v1/snapshots/{file_name}"
        task["status"] = "done"
        result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
        result_json_path.write_text(
            json.dumps(_serialize_national_task(task), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        task["status"] = "failed"
        task["message"] = str(exc) if str(exc) else ERROR_MSG["SCREENSHOT_FAILED"]
    finally:
        if page is not None:
            await page.close()

    await _send_callback_safely(task, origin, ctx)


async def _send_callback_safely(
    task: dict[str, Any], origin: str, ctx: NationSnapshotContext
) -> None:
    """发送回调，但不让回调异常中断任务结果落盘。"""

    try:
        await ctx.send_callback(task, origin)
    except Exception as exc:
        task["callbackError"] = str(exc)


async def _handle_national_background_task(
    task_id: str, origin: str, ctx: NationSnapshotContext
) -> None:
    """包装后台截图任务，串联并发控制和异常兜底。"""

    semaphore = ctx.get_screenshot_semaphore()
    if semaphore is None:
        await _run_national_task(task_id, origin, ctx)
        return

    async with semaphore:
        try:
            await _run_national_task(task_id, origin, ctx)
        except Exception as exc:
            task = ctx.task_store.get(task_id)
            if task:
                task["status"] = "failed"
                task["message"] = str(exc) or ERROR_MSG["TASK_EXECUTION_FAILED"]
                SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
                result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
                result_json_path.write_text(
                    json.dumps(
                        _serialize_national_task(task), ensure_ascii=False, indent=2
                    ),
                    encoding="utf-8",
                )


def register_national_snapshot_routes(
    router: APIRouter, ctx: NationSnapshotContext
) -> None:
    """向主应用注册全国截图相关路由。"""

    @router.get("/map-share", summary="全国地图渲染页")
    async def map_share(params: NationShareQuery = Depends()):
        task = ctx.task_store.get(params.taskId) or await _load_persisted_national_task(
            params.taskId, ctx
        )
        if not task:
            return _error(ctx, ERROR_MSG["TASK_NOT_FOUND"], 404)
        return HTMLResponse(_render_national_share_page(task))

    @router.post("/snapshot", summary="创建全国地图截图任务")
    async def national_snapshot_create(
        request: FastAPIRequest,
        body: NationSnapshotCreateRequest = Body(...),
    ):
        """创建全国地图截图任务，传入 regions，callback_url选填，会返回taskId"""

        task_id = ctx.generate_task_id()
        origin = ctx.get_origin(request)
        task = {
            "taskId": task_id,
            "taskType": "national",
            "status": "processing",
            "requestedRegions": [r.model_dump() for r in body.regions],
            "callbackUrl": ctx.normalize_callback_url(body.callback_url),
            "valueLabel": body.value_label or "状态",
            "regions": [],
            "failedRegions": [],
            "imageUrl": "",
            "mapUrl": f"{origin}/api/v1/map-share?taskId={task_id}",
            "createdAt": int(datetime.now().timestamp() * 1000),
        }
        ctx.task_store[task_id] = task

        asyncio.create_task(_handle_national_background_task(task_id, origin, ctx))

        return ctx.send_json(
            {
                "success": True,
                "data": {
                    "taskId": task_id,
                    "status": task["status"],
                    "valueLabel": task["valueLabel"],
                },
            }
        )
