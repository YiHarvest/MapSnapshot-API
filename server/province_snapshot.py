"""省级地图截图接口实现。

这个模块负责省级地图任务的请求校验、页面渲染、截图任务执行、
结果持久化和回调复用。用于展示某个省/市范围内的多个区域。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

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
class ProvinceSnapshotContext:
    """省级截图接口运行时依赖集合。

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
    infer_level: Callable[[str], str]
    get_region_index: Callable[[], Awaitable[dict[str, dict[str, Any]]]]


class ProvinceShareQuery:
    """省级地图渲染页查询参数。"""

    def __init__(self, taskId: str):
        self.taskId = taskId


class ProvinceRequest(BaseModel):
    """省级展示范围请求模型。"""

    name: str = Field(
        default="", description="选填，展示名称或兜底名称，不作为主匹配依据。"
    )
    adcode: str = Field(..., description="必填，province 的 adcode，作为主匹配依据。")

    @field_validator("adcode", "name", mode="before")
    @classmethod
    def normalize_string_fields(cls, value: Any) -> str:
        return str(value or "").strip()


class ProvinceRegionRequest(BaseModel):
    """省级内子区域请求模型。"""

    name: str = Field(
        default="", description="选填，子区域展示名称，不作为主匹配依据。"
    )
    adcode: str = Field(..., description="必填，子区域 adcode，作为主匹配依据。")
    value: str = Field(default="", description="选填，标注气泡中显示的内容。")

    @field_validator("name", "adcode", "value", mode="before")
    @classmethod
    def normalize_string_fields(cls, value: Any) -> str:
        return str(value or "").strip()


class ProvinceSnapshotCreateRequest(BaseModel):
    """省级截图任务创建请求模型。"""

    province: ProvinceRequest = Field(..., description="必填，地图展示范围。")
    regions: list[ProvinceRegionRequest] = Field(
        ..., description="必填，province 下的子区域列表，至少 1 项。"
    )
    value_label: str = Field(
        default="状态", description="选填，页面中 value 前展示的标签。"
    )
    callback_url: str = Field(default="", description="选填，任务完成后的回调地址。")

    @field_validator("value_label", "callback_url", mode="before")
    @classmethod
    def normalize_callback(cls, value: Any) -> str:
        return str(value or "").strip()


ProvinceRequest.model_rebuild()
ProvinceRegionRequest.model_rebuild()
ProvinceSnapshotCreateRequest.model_rebuild()


_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_JINJA_ENV = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=True, auto_reload=True)


def _error(ctx: ProvinceSnapshotContext, message: str, status_code: int = 400):
    """返回统一的错误 JSON。"""

    return ctx.send_json({"success": False, "message": message}, status_code)


def _normalize_adcode(value: Any) -> str:
    """把 adcode 统一转成去空格字符串。"""

    return str(value or "").strip()


def _normalize_name(value: Any) -> str:
    """把 name 统一转成去空格字符串。"""

    return str(value or "").strip()


def _looks_mojibake(value: Any) -> bool:
    """判断文本是否像乱码或替换字符。"""

    text = str(value or "")
    return "?" in text or "\ufffd" in text


def _choose_display_name(requested_name: str, matched_name: Any, adcode: str) -> str:
    """选择最终展示名称。

    优先使用调用方传入的可读 name，其次使用索引里的中文名，
    最后退回 adcode。
    """

    if (
        requested_name
        and requested_name != adcode
        and not _looks_mojibake(requested_name)
    ):
        return requested_name
    matched_text = str(matched_name or "").strip()
    if matched_text and not _looks_mojibake(matched_text):
        return matched_text
    return adcode


def _validate_payload(
    payload: dict[str, Any], ctx: ProvinceSnapshotContext
) -> tuple[dict[str, Any] | None, Any]:
    """校验并规范化 province-snapshot 请求体。"""

    province_data = payload.get("province")
    if not isinstance(province_data, dict):
        return None, _error(ctx, "province is required")

    province_adcode = _normalize_adcode(province_data.get("adcode"))
    if not province_adcode:
        return None, _error(ctx, "province.adcode is required")

    regions = payload.get("regions")
    if not isinstance(regions, list):
        return None, _error(ctx, "regions must be an array")
    if not regions:
        return None, _error(ctx, "regions must not be empty")

    normalized_regions: list[dict[str, str]] = []
    for index, region in enumerate(regions):
        if not isinstance(region, dict):
            return None, _error(ctx, f"regions[{index}] must be an object")
        region_adcode = _normalize_adcode(region.get("adcode"))
        if not region_adcode:
            return None, _error(ctx, f"regions[{index}].adcode is required")
        normalized_regions.append(
            {
                "adcode": region_adcode,
                "name": _normalize_name(region.get("name")),
                "value": str(region.get("value", "")).strip(),
            }
        )

    return (
        {
            "province": {
                "adcode": province_adcode,
                "name": _normalize_name(province_data.get("name")),
            },
            "regions": normalized_regions,
            "value_label": _normalize_name(payload.get("value_label")) or "状态",
            "callback_url": _normalize_name(payload.get("callback_url")),
        },
        None,
    )


async def _resolve_province(
    requested_province: dict[str, str], ctx: ProvinceSnapshotContext
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """根据 province.adcode 解析展示范围。"""

    index = await ctx.get_region_index()
    adcode = requested_province["adcode"]
    match = index["byAdcode"].get(adcode)
    if not match:
        return None, [
            {
                "name": requested_province["name"] or adcode,
                "reason": "province not found",
            }
        ]

    return (
        {
            "name": _choose_display_name(
                requested_province["name"], match.get("name"), adcode
            ),
            "adcode": adcode,
            "level": ctx.infer_level(adcode),
            "center": match.get("center"),
        },
        [],
    )


async def _resolve_regions(
    requested_regions: list[dict[str, str]], ctx: ProvinceSnapshotContext
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """根据 regions.adcode 解析子区域。"""

    index = await ctx.get_region_index()
    resolved: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []

    for region in requested_regions:
        adcode = region["adcode"]
        match = index["byAdcode"].get(adcode)
        if not match:
            failed.append(
                {"name": region["name"] or adcode, "reason": "region not found"}
            )
            continue
        resolved.append(
            {
                "name": _choose_display_name(region["name"], match.get("name"), adcode),
                "adcode": adcode,
                "level": ctx.infer_level(adcode),
                "value": region["value"],
                "center": match.get("center"),
            }
        )

    return resolved, failed


def _render_province_share_page(task: dict[str, Any]) -> str:
    """渲染省级地图页面 HTML。"""

    escaped_security_code = json.dumps(amap_security_code, ensure_ascii=False)
    template = _JINJA_ENV.get_template("province_share.html")

    return template.render(
        security_config_js=(
            f"window._AMapSecurityConfig = {escaped_security_code}"
            f" ? {{ securityJsCode: {escaped_security_code} }} : undefined;"
        ),
        amap_key=amap_key,
        task_data={
            "taskId": task["taskId"],
            "province": task["province"],
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


def _serialize_province_task(task: dict[str, Any]) -> dict[str, Any]:
    """把省级任务序列化成持久化 JSON。"""

    result = {
        "taskId": task["taskId"],
        "taskType": "province",
        "status": task["status"],
        "valueLabel": task.get("valueLabel") or "状态",
        "imageUrl": task.get("imageUrl", ""),
        "mapUrl": task.get("mapUrl", ""),
        "province": {
            "name": task.get("province", {}).get("name", ""),
            "adcode": task.get("province", {}).get("adcode", ""),
        },
        "regions": [
            {
                "name": region["name"],
                "adcode": region["adcode"],
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


async def _load_persisted_province_task(
    task_id: str, ctx: ProvinceSnapshotContext
) -> dict[str, Any] | None:
    """从磁盘恢复省级任务。

    这样服务重启后，之前生成的 province-share 链接仍然可打开。
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

    province = task.get("province")
    if not isinstance(province, dict):
        province = _infer_province_from_regions(regions)
        if not province:
            return None
        task["province"] = province

    task.setdefault("taskId", safe_task_id)
    await _enrich_persisted_task(task, ctx)
    return task


def _infer_province_from_regions(regions: list[Any]) -> dict[str, str] | None:
    """从子区域列表里反推 province 的省/市 adcode。"""

    adcodes = [
        str(region.get("adcode") or "").strip()
        for region in regions
        if isinstance(region, dict)
    ]
    adcodes = [adcode for adcode in adcodes if len(adcode) >= 6]
    if not adcodes:
        return None

    first = adcodes[0]
    if all(adcode[:4] == first[:4] for adcode in adcodes):
        adcode = first[:4] + "00"
        return {"name": adcode, "adcode": adcode, "level": "city"}
    if all(adcode[:2] == first[:2] for adcode in adcodes):
        adcode = first[:2] + "0000"
        return {"name": adcode, "adcode": adcode, "level": "province"}
    return None


async def _enrich_persisted_task(
    task: dict[str, Any], ctx: ProvinceSnapshotContext
) -> None:
    """补全持久化任务里缺失的中文名、层级和中心点。"""

    index = await ctx.get_region_index()

    province = task.get("province")
    if isinstance(province, dict):
        adcode = str(province.get("adcode") or "").strip()
        match = index["byAdcode"].get(adcode)
        if match:
            province["name"] = _choose_display_name(
                str(province.get("name") or "").strip(),
                match.get("name"),
                adcode,
            )
            province["level"] = province.get("level") or ctx.infer_level(adcode)
            province["center"] = province.get("center") or match.get("center")

    for region in task.get("regions", []):
        if not isinstance(region, dict):
            continue
        adcode = str(region.get("adcode") or "").strip()
        match = index["byAdcode"].get(adcode)
        if not match:
            continue
        region["name"] = _choose_display_name(
            str(region.get("name") or "").strip(),
            match.get("name"),
            adcode,
        )
        region["level"] = region.get("level") or ctx.infer_level(adcode)
        region["center"] = region.get("center") or match.get("center")


async def _run_province_task(
    task_id: str, origin: str, ctx: ProvinceSnapshotContext
) -> None:
    """执行省级截图任务的主流程。"""

    task = ctx.task_store.get(task_id)
    if not task:
        return

    if not amap_key:
        task["status"] = "failed"
        task["message"] = ERROR_MSG["MISSING_AMAP_KEY"]
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
        result_json_path.write_text(
            json.dumps(_serialize_province_task(task), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await _send_callback_safely(task, origin, ctx)
        return

    province, province_failed = await _resolve_province(task["requestedProvince"], ctx)
    regions, region_failed = await _resolve_regions(task["requestedRegions"], ctx)
    task["province"] = province or {}
    task["regions"] = regions
    task["failedRegions"] = [*province_failed, *region_failed]

    if task["failedRegions"] or not province or not regions:
        task["status"] = "failed"
        task["message"] = ERROR_MSG["REGIONS_NOT_FOUND"]
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
        result_json_path.write_text(
            json.dumps(_serialize_province_task(task), ensure_ascii=False, indent=2),
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
            json.dumps(_serialize_province_task(task), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        task["status"] = "failed"
        task["message"] = str(exc) if str(exc) else ERROR_MSG["SCREENSHOT_FAILED"]
        result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
        result_json_path.write_text(
            json.dumps(_serialize_province_task(task), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    finally:
        if page is not None:
            await page.close()

    await _send_callback_safely(task, origin, ctx)


async def _send_callback_safely(
    task: dict[str, Any], origin: str, ctx: ProvinceSnapshotContext
) -> None:
    """发送回调，但不让回调异常中断任务结果落盘。"""

    try:
        await ctx.send_callback(task, origin)
    except Exception as exc:
        task["callbackError"] = str(exc)


async def _handle_province_background_task(
    task_id: str, origin: str, ctx: ProvinceSnapshotContext
) -> None:
    """包装后台截图任务，串联并发控制和异常兜底。"""

    semaphore = ctx.get_screenshot_semaphore()
    if semaphore is None:
        await _run_province_task(task_id, origin, ctx)
        return

    async with semaphore:
        try:
            await _run_province_task(task_id, origin, ctx)
        except Exception as exc:
            task = ctx.task_store.get(task_id)
            if task:
                task["status"] = "failed"
                task["message"] = str(exc) or ERROR_MSG["TASK_EXECUTION_FAILED"]
                SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
                result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
                result_json_path.write_text(
                    json.dumps(
                        _serialize_province_task(task), ensure_ascii=False, indent=2
                    ),
                    encoding="utf-8",
                )


def register_province_snapshot_routes(
    router: APIRouter, ctx: ProvinceSnapshotContext
) -> None:
    """向主应用注册省级地图截图相关路由。"""

    @router.get("/province-share", summary="省级地图渲染页")
    async def province_share(params: ProvinceShareQuery = Depends()):
        task = ctx.task_store.get(params.taskId) or await _load_persisted_province_task(
            params.taskId, ctx
        )
        if not task:
            return _error(ctx, ERROR_MSG["TASK_NOT_FOUND"], 404)
        return HTMLResponse(_render_province_share_page(task))

    @router.post("/province-snapshot", summary="创建省级地图截图任务")
    async def province_snapshot_create(
        request: FastAPIRequest,
        body: ProvinceSnapshotCreateRequest = Body(...),
    ):
        """创建省级地图截图任务，传入 province + regions，callback_url选填，会返回taskId"""

        payload, error_response = _validate_payload(body.model_dump(), ctx)
        if error_response is not None:
            return error_response
        assert payload is not None

        task_id = ctx.generate_task_id()
        origin = ctx.get_origin(request)
        task = {
            "taskId": task_id,
            "taskType": "province",
            "status": "processing",
            "requestedProvince": payload["province"],
            "requestedRegions": payload["regions"],
            "valueLabel": payload["value_label"],
            "province": {},
            "callbackUrl": ctx.normalize_callback_url(payload["callback_url"]),
            "regions": [],
            "failedRegions": [],
            "imageUrl": "",
            "mapUrl": f"{origin}/api/v1/province-share?taskId={task_id}",
            "createdAt": int(datetime.now().timestamp() * 1000),
        }
        ctx.task_store[task_id] = task

        asyncio.create_task(_handle_province_background_task(task_id, origin, ctx))

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
