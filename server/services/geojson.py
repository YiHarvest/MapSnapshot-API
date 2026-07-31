"""GeoJSON 索引构建和行政区划解析。"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any

from server.core.config import PUBLIC_DIR
from server.core.runtime import RuntimeState
from server.services.naming import choose_display_name, infer_level, normalize_text


def _walk_coordinates(coordinates: Any, bounds: dict[str, float]) -> None:
    """递归遍历坐标数组，计算边界框。"""

    if not isinstance(coordinates, list) or not coordinates:
        return
    if (
        len(coordinates) >= 2
        and isinstance(coordinates[0], (int, float))
        and isinstance(coordinates[1], (int, float))
    ):
        longitude = float(coordinates[0])
        latitude = float(coordinates[1])
        bounds["minLng"] = min(bounds["minLng"], longitude)
        bounds["minLat"] = min(bounds["minLat"], latitude)
        bounds["maxLng"] = max(bounds["maxLng"], longitude)
        bounds["maxLat"] = max(bounds["maxLat"], latitude)
        return
    for item in coordinates:
        _walk_coordinates(item, bounds)


def _feature_center(feature: dict[str, Any]) -> list[float] | None:
    """计算 GeoJSON feature 的中心点，优先使用预设值，否则取边界框中心。"""

    properties = feature.get("properties") or {}
    for key in ("centroid", "center"):
        if isinstance(properties.get(key), list):
            return properties[key]

    bounds = {
        "minLng": float("inf"),
        "minLat": float("inf"),
        "maxLng": float("-inf"),
        "maxLat": float("-inf"),
    }
    _walk_coordinates((feature.get("geometry") or {}).get("coordinates"), bounds)
    if not math.isfinite(bounds["minLng"]) or not math.isfinite(bounds["minLat"]):
        return None
    return [
        (bounds["minLng"] + bounds["maxLng"]) / 2,
        (bounds["minLat"] + bounds["maxLat"]) / 2,
    ]


def _geojson_files() -> list[Path]:
    """获取所有 GeoJSON 文件路径，包括全国、省级和市级。"""

    root = PUBLIC_DIR / "geojson"
    files = [root / "china.json"]
    for directory in (root / "province", root / "city"):
        if directory.exists():
            files.extend(
                sorted(path for path in directory.rglob("*.json") if path.is_file())
            )
    return files


def _build_region_index() -> dict[str, dict[str, Any]]:
    """从 GeoJSON 文件构建行政区划索引，返回 adcode 和 name 双向映射。"""

    by_adcode: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for file_path in _geojson_files():
        if not file_path.exists():
            continue
        geojson = json.loads(file_path.read_text(encoding="utf-8"))
        for feature in geojson.get("features", []):
            properties = feature.get("properties") or {}
            name = normalize_text(properties.get("name"))
            adcode = normalize_text(properties.get("adcode"))
            center = _feature_center(feature)
            if not name or not center:
                continue
            record = {
                "name": name,
                "adcode": adcode,
                "level": properties.get("level") or infer_level(adcode),
                "center": center,
            }
            if adcode:
                by_adcode.setdefault(adcode, record)
            by_name.setdefault(name, record)
    return {"byAdcode": by_adcode, "byName": by_name}


async def build_region_index() -> dict[str, dict[str, Any]]:
    """在线程中读取 GeoJSON 并构建行政区划索引。"""

    return await asyncio.to_thread(_build_region_index)


class RegionService:
    """延迟加载的行政区划索引服务。"""

    def __init__(self, state: RuntimeState) -> None:
        self._state = state

    async def get_index(self) -> dict[str, dict[str, Any]]:
        """获取区域索引，首次调用时异步构建。"""

        if self._state.region_index is not None:
            return self._state.region_index
        if self._state.region_index_lock is None:
            self._state.region_index_lock = asyncio.Lock()
        async with self._state.region_index_lock:
            if self._state.region_index is None:
                self._state.region_index = await build_region_index()
        return self._state.region_index

    async def resolve_regions(
        self,
        requested_regions: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """解析请求的区域列表，返回成功和失败两个列表。"""

        index = await self.get_index()
        resolved: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for region in requested_regions:
            adcode = normalize_text(region.get("adcode"))
            name = normalize_text(region.get("name"))
            match = (index["byAdcode"].get(adcode) if adcode else None) or (
                index["byName"].get(name) if name else None
            )
            if not match:
                failed.append(
                    {
                        "name": name or adcode or "unknown region",
                        "reason": "region not found",
                    }
                )
                continue
            resolved.append(
                {
                    "name": choose_display_name(name, match["name"], adcode),
                    "adcode": match["adcode"],
                    "level": match["level"],
                    "value": normalize_text(region.get("value")),
                    "center": match["center"],
                }
            )
        return resolved, failed
