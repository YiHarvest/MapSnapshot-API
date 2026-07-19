"""市级地图截图接口实现。

这个模块负责市级地图任务的请求校验、页面渲染、截图任务执行、
结果持久化和回调复用。用户传入一个市和这个市中若干个区或者县，
然后进行展示和截图。
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
class CitySnapshotContext:
    """市级截图接口运行时依赖集合。

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


class CityShareQuery:
    """市级地图渲染页查询参数。"""

    def __init__(self, taskId: str):
        self.taskId = taskId


class CityRequest(BaseModel):
    """市请求模型。"""

    name: str = Field(default="", description="选填，市的展示名称，不作为主匹配依据。")
    adcode: str = Field(..., description="必填，市的 adcode。")

    @field_validator("adcode", "name", mode="before")
    @classmethod
    def normalize_string_fields(cls, value: Any) -> str:
        return str(value or "").strip()


class DistrictRequest(BaseModel):
    """区/县请求模型。"""

    name: str = Field(
        default="", description="选填，区/县的展示名称，不作为主匹配依据。"
    )
    adcode: str = Field(..., description="必填，区/县的 adcode。")
    value: str = Field(default="", description="选填，标注气泡中显示的内容。")

    @field_validator("name", "adcode", "value", mode="before")
    @classmethod
    def normalize_string_fields(cls, value: Any) -> str:
        return str(value or "").strip()


class CitySnapshotCreateRequest(BaseModel):
    """市级截图任务创建请求模型。"""

    city: CityRequest = Field(..., description="必填，地图展示的市。")
    districts: list[DistrictRequest] = Field(
        ..., description="必填，市下的区/县列表，至少 1 项。"
    )
    value_label: str = Field(
        default="状态", description="选填，页面中 value 前展示的标签。"
    )
    callback_url: str = Field(default="", description="选填，任务完成后的回调地址。")

    @field_validator("value_label", "callback_url", mode="before")
    @classmethod
    def normalize_callback(cls, value: Any) -> str:
        return str(value or "").strip()


CityRequest.model_rebuild()
DistrictRequest.model_rebuild()
CitySnapshotCreateRequest.model_rebuild()


_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_JINJA_ENV = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=True, auto_reload=True)


def _error(ctx: CitySnapshotContext, message: str, status_code: int = 400):
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
    payload: dict[str, Any], ctx: CitySnapshotContext
) -> tuple[dict[str, Any] | None, Any]:
    """校验并规范化 city-snapshot 请求体。"""

    if not isinstance(payload, dict):
        return None, _error(ctx, "request body must be an object")

    city = payload.get("city")
    if not isinstance(city, dict):
        return None, _error(ctx, "city is required")

    city_adcode = _normalize_adcode(city.get("adcode"))
    if not city_adcode:
        return None, _error(ctx, "city.adcode is required")

    if not city_adcode.endswith("00"):
        return None, _error(ctx, "city adcode must end with '00'")

    districts = payload.get("districts")
    if not isinstance(districts, list):
        return None, _error(ctx, "districts must be an array")
    if not districts:
        return None, _error(ctx, "districts must not be empty")

    normalized_districts: list[dict[str, str]] = []
    for index, district in enumerate(districts):
        if not isinstance(district, dict):
            return None, _error(ctx, f"districts[{index}] must be an object")
        district_adcode = _normalize_adcode(district.get("adcode"))
        if district_adcode.endswith("00"):
            return None, _error(
                ctx, f"districts[{index}] adcode must not end with '00'"
            )

        normalized_districts.append(
            {
                "adcode": district_adcode,
                "name": _normalize_name(district.get("name")),
                "value": str(district.get("value", "")).strip(),
            }
        )

    return (
        {
            "city": {
                "adcode": city_adcode,
                "name": _normalize_name(city.get("name")),
            },
            "districts": normalized_districts,
            "value_label": _normalize_name(payload.get("value_label")) or "状态",
            "callback_url": _normalize_name(payload.get("callback_url")),
        },
        None,
    )


async def _resolve_city(
    requested_city: dict[str, str], ctx: CitySnapshotContext
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """根据 city.adcode 解析展示范围。"""

    index = await ctx.get_region_index()
    adcode = requested_city["adcode"]
    match = index["byAdcode"].get(adcode)
    if not match:
        return None, [
            {"name": requested_city["name"] or adcode, "reason": "city not found"}
        ]

    return (
        {
            "name": _choose_display_name(
                requested_city["name"], match.get("name"), adcode
            ),
            "adcode": adcode,
            "level": "city",
            "center": match.get("center"),
        },
        [],
    )


async def _resolve_districts(
    requested_districts: list[dict[str, str]], ctx: CitySnapshotContext
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """根据 districts.adcode 解析区/县。"""

    index = await ctx.get_region_index()
    resolved: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []

    for district in requested_districts:
        adcode = district["adcode"]
        match = index["byAdcode"].get(adcode)
        if not match:
            failed.append(
                {"name": district["name"] or adcode, "reason": "district not found"}
            )
            continue
        resolved.append(
            {
                "name": _choose_display_name(
                    district["name"], match.get("name"), adcode
                ),
                "adcode": adcode,
                "level": ctx.infer_level(adcode),
                "value": district["value"],
                "center": match.get("center"),
            }
        )

    return resolved, failed


def _render_city_share_page(task: dict[str, Any]) -> str:
    """渲染市级地图页面 HTML。"""

    escaped_security_code = json.dumps(amap_security_code, ensure_ascii=False)
    template = _JINJA_ENV.get_template("city_share.html")

    return template.render(
        security_config_js=(
            f"window._AMapSecurityConfig = {escaped_security_code}"
            f" ? {{ securityJsCode: {escaped_security_code} }} : undefined;"
        ),
        amap_key=amap_key,
        task_data={
            "taskId": task["taskId"],
            "city": task["city"],
            "districts": task["districts"],
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


def _serialize_city_task(task: dict[str, Any]) -> dict[str, Any]:
    """把市级任务序列化成持久化 JSON。"""

    result = {
        "taskId": task["taskId"],
        "taskType": "city",
        "status": task["status"],
        "valueLabel": task.get("valueLabel") or "状态",
        "imageUrl": task.get("imageUrl", ""),
        "mapUrl": task.get("mapUrl", ""),
        "city": {
            "name": task.get("city", {}).get("name", ""),
            "adcode": task.get("city", {}).get("adcode", ""),
        },
        "districts": [
            {
                "name": district["name"],
                "adcode": district["adcode"],
                "value": district["value"],
            }
            for district in task.get("districts", [])
        ],
    }

    if task.get("failedDistricts"):
        result["failedDistricts"] = task["failedDistricts"]
    if task.get("callbackUrl"):
        result["callback"] = {
            "url": task["callbackUrl"],
            "error": task.get("callbackError"),
        }

    return result


async def _load_persisted_city_task(
    task_id: str, ctx: CitySnapshotContext
) -> dict[str, Any] | None:
    """从磁盘恢复市级任务。

    这样服务重启后，之前生成的 city-share 链接仍然可打开。
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

    districts = task.get("districts")
    if not isinstance(districts, list):
        return None

    city = task.get("city")
    if not isinstance(city, dict):
        return None

    task.setdefault("taskId", safe_task_id)
    await _enrich_persisted_city_task(task, ctx)
    return task


async def _enrich_persisted_city_task(
    task: dict[str, Any], ctx: CitySnapshotContext
) -> None:
    """补全持久化任务里缺失的中文名、层级和中心点。"""

    index = await ctx.get_region_index()

    city = task.get("city")
    if isinstance(city, dict):
        adcode = str(city.get("adcode") or "").strip()
        match = index["byAdcode"].get(adcode)
        if match:
            city["name"] = _choose_display_name(
                str(city.get("name") or "").strip(),
                match.get("name"),
                adcode,
            )
            city["level"] = "city"
            city["center"] = city.get("center") or match.get("center")

    for district in task.get("districts", []):
        if not isinstance(district, dict):
            continue
        adcode = str(district.get("adcode") or "").strip()
        match = index["byAdcode"].get(adcode)
        if not match:
            continue
        district["name"] = _choose_display_name(
            str(district.get("name") or "").strip(),
            match.get("name"),
            adcode,
        )
        district["level"] = district.get("level") or ctx.infer_level(adcode)
        district["center"] = district.get("center") or match.get("center")


async def _run_city_task(task_id: str, origin: str, ctx: CitySnapshotContext) -> None:
    """执行市级截图任务的主流程。"""

    task = ctx.task_store.get(task_id)
    if not task:
        return

    if not amap_key:
        task["status"] = "failed"
        task["message"] = ERROR_MSG["MISSING_AMAP_KEY"]
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
        result_json_path.write_text(
            json.dumps(_serialize_city_task(task), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await _send_callback_safely(task, origin, ctx)
        return

    city, city_failed = await _resolve_city(task["requestedCity"], ctx)
    districts, district_failed = await _resolve_districts(
        task["requestedDistricts"], ctx
    )
    task["city"] = city or {}
    task["districts"] = districts
    task["failedDistricts"] = [*city_failed, *district_failed]

    if task["failedDistricts"] or not city or not districts:
        task["status"] = "failed"
        task["message"] = ERROR_MSG["REGIONS_NOT_FOUND"]
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
        result_json_path.write_text(
            json.dumps(_serialize_city_task(task), ensure_ascii=False, indent=2),
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
            json.dumps(_serialize_city_task(task), ensure_ascii=False, indent=2),
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
    task: dict[str, Any], origin: str, ctx: CitySnapshotContext
) -> None:
    """发送回调，但不让回调异常中断任务结果落盘。"""

    try:
        await ctx.send_callback(task, origin)
    except Exception as exc:
        task["callbackError"] = str(exc)


async def _handle_city_background_task(
    task_id: str, origin: str, ctx: CitySnapshotContext
) -> None:
    """包装后台截图任务，串联并发控制和异常兜底。"""

    semaphore = ctx.get_screenshot_semaphore()
    if semaphore is None:
        await _run_city_task(task_id, origin, ctx)
        return

    async with semaphore:
        try:
            await _run_city_task(task_id, origin, ctx)
        except Exception as exc:
            task = ctx.task_store.get(task_id)
            if task:
                task["status"] = "failed"
                task["message"] = str(exc) or ERROR_MSG["TASK_EXECUTION_FAILED"]
                SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
                result_json_path = SNAPSHOT_DIR / f"{task_id}.json"
                result_json_path.write_text(
                    json.dumps(
                        _serialize_city_task(task), ensure_ascii=False, indent=2
                    ),
                    encoding="utf-8",
                )


def register_city_snapshot_routes(router: APIRouter, ctx: CitySnapshotContext) -> None:
    """向主应用注册市级截图相关路由。"""

    @router.get("/city-share", summary="市级地图渲染页")
    async def city_share(params: CityShareQuery = Depends()):
        task = ctx.task_store.get(params.taskId) or await _load_persisted_city_task(
            params.taskId, ctx
        )
        if not task:
            return _error(ctx, ERROR_MSG["TASK_NOT_FOUND"], 404)
        return HTMLResponse(_render_city_share_page(task))

    @router.post("/city-snapshot", summary="创建市级地图截图任务")
    async def city_snapshot_create(
        request: FastAPIRequest,
        body: CitySnapshotCreateRequest = Body(...),
    ):
        """创建市级地图截图任务，传入 city + districts，callback_url选填，会返回taskId"""

        payload, error_response = _validate_payload(body.model_dump(), ctx)
        if error_response is not None:
            return error_response
        assert payload is not None

        task_id = ctx.generate_task_id()
        origin = ctx.get_origin(request)
        task = {
            "taskId": task_id,
            "taskType": "city",
            "status": "processing",
            "requestedCity": payload["city"],
            "requestedDistricts": payload["districts"],
            "valueLabel": payload["value_label"],
            "city": {},
            "callbackUrl": ctx.normalize_callback_url(payload["callback_url"]),
            "districts": [],
            "failedDistricts": [],
            "imageUrl": "",
            "mapUrl": f"{origin}/api/v1/city-share?taskId={task_id}",
            "createdAt": int(datetime.now().timestamp() * 1000),
        }
        ctx.task_store[task_id] = task

        asyncio.create_task(_handle_city_background_task(task_id, origin, ctx))

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
