#!/usr/bin/env python
"""地图标记截图服务（FastAPI 版本）。

提供 REST API 用于创建和查询地图截图任务。
基于 Playwright 无头浏览器对高德地图进行屏幕截图。
"""
import html

import asyncio
import json
import math
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse
from urllib.request import Request as URLRequest, urlopen

from fastapi import (
    FastAPI,
    HTTPException,
    Request as FastAPIRequest,
    APIRouter,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# TODO yqy: 已删除无用导入，各模块自己导入配置
try:
    from server.config import (
        BASE_URL,
        CLEANUP_INTERVAL_SECONDS,
        EDGE_EXECUTABLE_PATHS,
        ERROR_MSG,
        PUBLIC_DIR,
        REGION_NOT_FOUND_REASON,
        SCREENSHOT_CONCURRENCY,
        SERVER_RELOAD,
        SNAPSHOT_DIR,
        TASK_MAX_AGE_SECONDS,
        UNKNOWN_REGION_NAME,
        port,
        playwright_executable_path,
    )
except ImportError:
    from config import (  # type: ignore
        BASE_URL,
        CLEANUP_INTERVAL_SECONDS,
        EDGE_EXECUTABLE_PATHS,
        ERROR_MSG,
        PUBLIC_DIR,
        REGION_NOT_FOUND_REASON,
        SCREENSHOT_CONCURRENCY,
        SERVER_RELOAD,
        SNAPSHOT_DIR,
        TASK_MAX_AGE_SECONDS,
        UNKNOWN_REGION_NAME,
        port,
        playwright_executable_path,
    )

# 全局变量
task_store: dict[str, dict[str, Any]] = {}
region_index_cache: Optional[dict[str, dict[str, Any]]] = None
region_index_lock: Optional[asyncio.Lock] = None

_cleanup_task: Optional[asyncio.Task[None]] = None
_browser_pool: dict[str, Any] = {"playwright": None, "browser": None}
_screenshot_semaphore: Optional[asyncio.Semaphore] = None


async def _cleanup_expired_tasks() -> None:
    """删除超过保留时长的任务记录和截图文件。"""
    now_ts = int(datetime.now().timestamp() * 1000)
    cutoff_ts = now_ts - TASK_MAX_AGE_SECONDS * 1000
    expired_ids: list[str] = []

    for task_id, task in list(task_store.items()):
        created = task.get("createdAt", 0)
        if created < cutoff_ts:
            expired_ids.append(task_id)

    for task_id in expired_ids:
        del task_store[task_id]
        for ext in (".png", ".json"):
            file_path = SNAPSHOT_DIR / f"{task_id}{ext}"
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                pass

    if expired_ids:
        print(f"[cleanup] removed {len(expired_ids)} expired task(s)")


async def _run_cleanup_loop() -> None:
    """后台循环：每周清理一次过期任务。"""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        await _cleanup_expired_tasks()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动清理后台任务和浏览器池，关闭时释放资源。"""
    global _cleanup_task, _screenshot_semaphore
    _cleanup_task = asyncio.create_task(_run_cleanup_loop())
    _screenshot_semaphore = asyncio.Semaphore(SCREENSHOT_CONCURRENCY)
    print("[cleanup] background cleanup task started (1-week TTL)")

    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    try:
        executable_path = get_browser_executable_path()
        if executable_path:
            browser = await playwright.chromium.launch(
                executable_path=executable_path,
                headless=True,
                args=["--disable-gpu"],
            )
        else:
            browser = await playwright.chromium.launch(headless=True)
        _browser_pool["playwright"] = playwright
        _browser_pool["browser"] = browser
        print(
            f"[browser] browser pool started (max concurrency: {SCREENSHOT_CONCURRENCY})"
        )
    except Exception:
        await playwright.stop()
        raise

    yield

    if _browser_pool["browser"]:
        await _browser_pool["browser"].close()
    if _browser_pool["playwright"]:
        await _browser_pool["playwright"].stop()
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Region View Snapshot Server",
    lifespan=lifespan,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/geojson", StaticFiles(directory=str(PUBLIC_DIR / "geojson")), name="geojson")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api/v1")


def send_json(payload: dict[str, Any], status_code: int = 200):
    """返回 JSON 格式的 FastAPI 响应。"""
    from fastapi.responses import JSONResponse

    return JSONResponse(payload, status_code=status_code)


def get_origin(request: FastAPIRequest) -> str:
    """从请求头中提取服务来源的完整 URL。"""
    host = request.headers.get("host") or f"127.0.0.1:{port}"
    protocol = request.headers.get("x-forwarded-proto") or "http"
    return f"{protocol}://{host}{BASE_URL}"


def generate_task_id() -> str:
    """生成唯一任务 ID。"""
    return uuid.uuid4().hex


def walk_coordinates(coordinates: Any, bounds: dict[str, float]) -> None:
    """递归遍历 GeoJSON 坐标数组，计算边界范围。"""
    if not isinstance(coordinates, list) or not coordinates:
        return

    if (
        len(coordinates) >= 2
        and isinstance(coordinates[0], (int, float))
        and isinstance(coordinates[1], (int, float))
    ):
        lng = float(coordinates[0])
        lat = float(coordinates[1])
        bounds["minLng"] = min(bounds["minLng"], lng)
        bounds["minLat"] = min(bounds["minLat"], lat)
        bounds["maxLng"] = max(bounds["maxLng"], lng)
        bounds["maxLat"] = max(bounds["maxLat"], lat)
        return

    for item in coordinates:
        walk_coordinates(item, bounds)


def infer_level(adcode: str) -> str:
    """根据行政区划代码推断区域层级。"""
    if not adcode:
        return "province"
    if adcode.endswith("0000"):
        return "province"
    if adcode.endswith("00"):
        return "city"
    return "district"


def looks_mojibake(value: Any) -> bool:
    """判断文本是否像乱码、占位符或不可读字符。"""
    text = str(value or "")
    return "?" in text or "\ufffd" in text


def get_feature_center(feature: dict[str, Any]) -> Optional[list[float]]:
    """获取 GeoJSON 要素的中心点坐标。"""
    properties = feature.get("properties") or {}
    if isinstance(properties.get("centroid"), list):
        return properties["centroid"]
    if isinstance(properties.get("center"), list):
        return properties["center"]

    bounds = {
        "minLng": float("inf"),
        "minLat": float("inf"),
        "maxLng": float("-inf"),
        "maxLat": float("-inf"),
    }
    geometry = feature.get("geometry") or {}
    walk_coordinates(geometry.get("coordinates"), bounds)

    if not math.isfinite(bounds["minLng"]) or not math.isfinite(bounds["minLat"]):
        return None

    return [
        (bounds["minLng"] + bounds["maxLng"]) / 2,
        (bounds["minLat"] + bounds["maxLat"]) / 2,
    ]


def collect_geojson_files(dir_path: Path) -> list[Path]:
    """递归收集目录下所有 JSON 文件。"""
    if not dir_path.exists():
        return []
    return [path for path in sorted(dir_path.rglob("*.json")) if path.is_file()]


def build_region_index_sync() -> dict[str, dict[str, Any]]:
    """同步构建全局区域索引。"""
    by_adcode: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    geojson_files = [
        PUBLIC_DIR / "geojson" / "china.json",
        *collect_geojson_files(PUBLIC_DIR / "geojson" / "province"),
        *collect_geojson_files(PUBLIC_DIR / "geojson" / "city"),
    ]

    for file_path in geojson_files:
        if not file_path.exists():
            continue
        geojson = json.loads(file_path.read_text(encoding="utf-8"))
        for feature in geojson.get("features", []):
            properties = feature.get("properties") or {}
            name = properties.get("name")
            adcode = str(properties.get("adcode") or "")
            center = get_feature_center(feature)
            if not name or not center:
                continue

            record = {
                "name": name,
                "adcode": adcode,
                "level": properties.get("level") or infer_level(adcode),
                "center": center,
            }

            if adcode and adcode not in by_adcode:
                by_adcode[adcode] = record
            if name not in by_name:
                by_name[name] = record

    return {"byAdcode": by_adcode, "byName": by_name}


async def get_region_index() -> dict[str, dict[str, Any]]:
    """获取区域索引（懒加载 + 异步缓存）。"""
    global region_index_cache, region_index_lock
    if region_index_cache is not None:
        return region_index_cache
    if region_index_lock is None:
        region_index_lock = asyncio.Lock()
    async with region_index_lock:
        if region_index_cache is None:
            region_index_cache = await asyncio.to_thread(build_region_index_sync)
        return region_index_cache


async def resolve_regions(
    input_regions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """根据用户输入的 regions 列表解析实际区域坐标。"""
    index = await get_region_index()
    resolved: list[dict[str, Any]] = []
    failed_regions: list[dict[str, Any]] = []

    for region in input_regions:
        adcode = str(region.get("adcode") or "")
        name = str(region.get("name") or "").strip()
        match = (index["byAdcode"].get(adcode) if adcode else None) or (
            index["byName"].get(name) if name else None
        )

        if not match:
            failed_regions.append(
                {
                    "name": name or adcode or UNKNOWN_REGION_NAME,
                    "reason": REGION_NOT_FOUND_REASON,
                }
            )
            continue

        resolved_name = name
        if not resolved_name or looks_mojibake(resolved_name):
            index_name = match["name"]
            resolved_name = index_name if not looks_mojibake(index_name) else adcode

        resolved.append(
            {
                "name": resolved_name,
                "adcode": match["adcode"],
                "level": match["level"],
                "value": str(region.get("value", "")).strip(),
                "center": match["center"],
            }
        )

    return resolved, failed_regions


def normalize_callback_url(callback_url: str | None) -> str:
    """规范化回调 URL，仅允许 http/https 协议。"""
    if not callback_url:
        return ""
    try:
        parsed = urlparse(callback_url)
        if parsed.scheme not in {"http", "https"}:
            return ""
        if not parsed.netloc:
            return ""
        return urlunparse(parsed)
    except Exception:
        return ""


def serialize_task(task: dict[str, Any]) -> dict[str, Any]:
    """将内部任务对象序列化为对外返回的 JSON 数据。"""
    result: dict[str, Any]
    if task["status"] == "done":
        if task.get("taskType") == "province":
            result = {
                "taskId": task["taskId"],
                "status": task["status"],
                "valueLabel": task.get("valueLabel") or "状态",
                "imageUrl": task["imageUrl"],
                "mapUrl": task["mapUrl"],
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
                    for region in task["regions"]
                ],
            }
        elif task.get("taskType") == "city":
            result = {
                "taskId": task["taskId"],
                "status": task["status"],
                "valueLabel": task.get("valueLabel") or "状态",
                "imageUrl": task["imageUrl"],
                "mapUrl": task["mapUrl"],
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
                    for district in task["districts"]
                ],
            }
        else:  # national
            result = {
                "taskId": task["taskId"],
                "status": task["status"],
                "valueLabel": task.get("valueLabel") or "状态",
                "imageUrl": task["imageUrl"],
                "mapUrl": task["mapUrl"],
                "regions": [
                    {
                        "name": region["name"],
                        "adcode": region["adcode"],
                        "level": region["level"],
                        "value": region["value"],
                    }
                    for region in task["regions"]
                ],
            }
    elif task["status"] == "failed":
        if task.get("taskType") == "city":
            result = {
                "taskId": task["taskId"],
                "status": task["status"],
                "valueLabel": task.get("valueLabel") or "状态",
                "message": task.get("message") or "task failed",
                "city": task.get("city", {}),
                "districts": task.get("districts", []),
                "failedDistricts": task.get("failedDistricts", []),
            }
        elif task.get("taskType") == "province":
            result = {
                "taskId": task["taskId"],
                "status": task["status"],
                "valueLabel": task.get("valueLabel") or "状态",
                "message": task.get("message") or "task failed",
                "province": task.get("province", {}),
                "regions": task.get("regions", []),
                "failedRegions": task.get("failedRegions", []),
            }
        else:  # national
            result = {
                "taskId": task["taskId"],
                "status": task["status"],
                "valueLabel": task.get("valueLabel") or "状态",
                "message": task.get("message") or "task failed",
                "regions": task.get("regions", []),
                "failedRegions": task.get("failedRegions", []),
            }
    else:
        result = {
            "taskId": task["taskId"],
            "status": task["status"],
            "valueLabel": task.get("valueLabel") or "状态",
        }

    if task.get("callbackUrl"):
        result["callback"] = {
            "url": task["callbackUrl"],
            "error": task.get("callbackError"),
        }

    return result


async def send_callback(task: dict[str, Any], origin: str) -> None:
    """任务完成后向调用方发送 POST 回调通知。"""
    callback_url = task.get("callbackUrl")
    if not callback_url:
        return

    # TODO yqy: send_callback 函数需要根据 taskType 区分回调 payload 结构
    # 市级接口(city)使用 districts 和 failedDistricts，而不是 regions 和 failedRegions
    if task.get("taskType") == "city":
        callback_payload: dict[str, Any] = {
            "taskId": task["taskId"],
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
            callback_payload["failedDistricts"] = task["failedDistricts"]
    elif task.get("taskType") == "province":
        callback_payload: dict[str, Any] = {
            "taskId": task["taskId"],
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
            callback_payload["failedRegions"] = task["failedRegions"]
    else:  # national
        callback_payload: dict[str, Any] = {
            "taskId": task["taskId"],
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
            callback_payload["failedRegions"] = task["failedRegions"]

    data = json.dumps(callback_payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Map-Snapshot-Task-Id": task["taskId"],
        "X-Map-Snapshot-Origin": origin,
    }

    def _post() -> None:
        request = URLRequest(callback_url, data=data, headers=headers, method="POST")
        with urlopen(request, timeout=30) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"{ERROR_MSG['CALLBACK_FAILED']}: {response.status}")

    try:
        await asyncio.to_thread(_post)
    except Exception as exc:
        raise RuntimeError(f"{ERROR_MSG['CALLBACK_FAILED']}: {exc}") from exc


def get_browser_executable_path() -> Optional[str]:
    """获取浏览器可执行文件路径。"""
    if playwright_executable_path and Path(playwright_executable_path).exists():
        return playwright_executable_path
    for candidate in EDGE_EXECUTABLE_PATHS:
        if Path(candidate).exists():
            return candidate
    return None


# 路由定义
@app.get("/dO3j6iTFfD.txt")
async def _():
    """返回静态文本文件内容。"""
    return FileResponse(STATIC_DIR / "dO3j6iTFfD.txt")
    
@router.get("/health")
def health_check():
    """健康检查接口。"""
    return {"status": "ok", "service": "region-view-snapshot-server"}


@router.get("/snapshots/{file_name}")
def get_snapshot(file_name: str):
    """返回截图 PNG 文件。"""
    safe_name = Path(file_name).name
    file_path = SNAPSHOT_DIR / safe_name

    if file_path.suffix.lower() != ".png" or not file_path.exists():
        raise HTTPException(status_code=404, detail=ERROR_MSG["IMAGE_NOT_FOUND"])

    return FileResponse(
        path=str(file_path),
        media_type="image/png",
        filename=safe_name,
        headers={"Cache-Control": "public, max-age=31536000"},
    )


@router.get("/snapshot/{task_id}")
async def snapshot_query(task_id: str):
    """查询任务状态和结果。"""
    task = task_store.get(task_id)
    if not task:
        from fastapi.responses import JSONResponse

        # 尝试从磁盘加载
        safe_task_id = Path(task_id).name
        result_path = SNAPSHOT_DIR / f"{safe_task_id}.json"
        if result_path.exists():
            try:
                task = json.loads(result_path.read_text(encoding="utf-8"))
                status_code = 500 if task.get("status") == "failed" else 200
                return JSONResponse(
                    {
                        "success": task.get("status") != "failed",
                        "data": serialize_task(task),
                    },
                    status_code,
                )
            except (OSError, json.JSONDecodeError):
                pass

        return send_json(
            {"success": False, "message": ERROR_MSG["TASK_NOT_FOUND"]}, 404
        )

    status_code = 500 if task["status"] == "failed" else 200
    return send_json(
        {
            "success": task["status"] != "failed",
            "data": serialize_task(task),
        },
        status_code,
    )


# 注册全国接口路由
try:
    from server.nation_snapshot import (
        NationSnapshotContext,
        register_national_snapshot_routes,
    )
except ImportError:
    from nation_snapshot import (  # type: ignore
        NationSnapshotContext,
        register_national_snapshot_routes,
    )

register_national_snapshot_routes(
    router,
    NationSnapshotContext(
        task_store=task_store,
        browser_pool=_browser_pool,
        get_screenshot_semaphore=lambda: _screenshot_semaphore,
        generate_task_id=generate_task_id,
        get_origin=get_origin,
        normalize_callback_url=normalize_callback_url,
        send_json=send_json,
        send_callback=send_callback,
        serialize_task=serialize_task,
        get_region_index=get_region_index,
        resolve_regions=resolve_regions,
    ),
)

# 注册省级接口路由
try:
    from server.province_snapshot import (
        ProvinceSnapshotContext,
        register_province_snapshot_routes,
    )
except ImportError:
    from province_snapshot import (  # type: ignore
        ProvinceSnapshotContext,
        register_province_snapshot_routes,
    )

register_province_snapshot_routes(
    router,
    ProvinceSnapshotContext(
        task_store=task_store,
        browser_pool=_browser_pool,
        get_screenshot_semaphore=lambda: _screenshot_semaphore,
        generate_task_id=generate_task_id,
        get_origin=get_origin,
        normalize_callback_url=normalize_callback_url,
        send_json=send_json,
        send_callback=send_callback,
        serialize_task=serialize_task,
        infer_level=infer_level,
        get_region_index=get_region_index,
    ),
)

# 注册市级接口路由
try:
    from server.city_snapshot import (
        CitySnapshotContext,
        register_city_snapshot_routes,
    )
except ImportError:
    from city_snapshot import (  # type: ignore
        CitySnapshotContext,
        register_city_snapshot_routes,
    )

register_city_snapshot_routes(
    router,
    CitySnapshotContext(
        task_store=task_store,
        browser_pool=_browser_pool,
        get_screenshot_semaphore=lambda: _screenshot_semaphore,
        generate_task_id=generate_task_id,
        get_origin=get_origin,
        normalize_callback_url=normalize_callback_url,
        send_json=send_json,
        send_callback=send_callback,
        serialize_task=serialize_task,
        infer_level=infer_level,
        get_region_index=get_region_index,
    ),
)

app.include_router(router)

if __name__ == "__main__":
    import sys
    import uvicorn

    if SERVER_RELOAD:
        sys.path.insert(0, str(BASE_DIR.parent))
        uvicorn.run(
            "server.app:app",
            host="0.0.0.0",
            port=port,
            reload=True,
            reload_dirs=[str(BASE_DIR), str(PUBLIC_DIR / "geojson")],
        )
    else:
        uvicorn.run(app, host="0.0.0.0", port=port)
