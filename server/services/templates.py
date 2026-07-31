"""Jinja 模板渲染环境。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from server.core.config import (
    MAP_COMPLETE_DELAY_MS,
    MAP_READY_FALLBACK_TIMEOUT_MS,
    MULTI_FITVIEW_PADDING,
    SHARE_MAP_ZOOM,
    SHARE_MAP_ZOOMS,
    SHARE_POLYGON_STYLE,
    SINGLE_FITVIEW_PADDING,
    SINGLE_REGION_DEFAULT_ZOOM,
    SINGLE_REGION_ZOOM,
    amap_key,
    amap_security_code,
)

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
SHARE_COMMON_JS = TEMPLATE_DIR.parent / "static" / "js" / "share-common.js"
JINJA_ENV = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(("html", "xml")),
    auto_reload=True,
)


def _render_share_template(
    template_name: str,
    task_data: dict[str, Any],
) -> str:
    escaped_security_code = json.dumps(amap_security_code, ensure_ascii=False)
    share_common_version = hashlib.sha256(SHARE_COMMON_JS.read_bytes()).hexdigest()[:12]
    return JINJA_ENV.get_template(template_name).render(
        security_config_js=(
            f"window._AMapSecurityConfig = {escaped_security_code}"
            f" ? {{ securityJsCode: {escaped_security_code} }} : undefined;"
        ),
        amap_key=amap_key,
        task_data=task_data,
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
        share_common_version=share_common_version,
    )


async def render_share_template(
    template_name: str,
    task_data: dict[str, Any],
) -> str:
    """在线程中渲染分享页面，避免模板文件 I/O 阻塞事件循环。"""

    return await asyncio.to_thread(_render_share_template, template_name, task_data)
