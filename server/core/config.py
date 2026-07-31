"""环境变量和渲染配置。"""

from __future__ import annotations

import os
from pathlib import Path

# 路径配置
ROOT_DIR = Path(__file__).resolve().parents[2]
PUBLIC_DIR = ROOT_DIR / "public"
SNAPSHOT_DIR = PUBLIC_DIR / "snapshots"

# 服务配置
DEFAULT_PORT = int(os.getenv("MAP_SNAPSHOT_PORT") or os.getenv("PORT") or "28787")
BASE_URL = os.getenv("SNAPSHOT_BASE_URL", "").rstrip("/")

VIEWPORT = {"width": 1280, "height": 820}
DEVICE_SCALE_FACTOR = 1
SCREENSHOT_CONCURRENCY = 2

# 地图加载超时配置
MAP_READY_TIMEOUT_MS = 30000
SCREENSHOT_DELAY_MS = 1200
MAP_READY_FALLBACK_TIMEOUT_MS = 10000
MAP_COMPLETE_DELAY_MS = 5000

# 地图显示配置
SHARE_MAP_ZOOM = 7
SHARE_MAP_ZOOMS = [3, 18]
SINGLE_REGION_ZOOM = {
    "province": 6,
    "city": 9,
    "district": 10,
}
SINGLE_REGION_DEFAULT_ZOOM = 10
MULTI_FITVIEW_PADDING = [70, 70, 70, 70]
SINGLE_FITVIEW_PADDING = [110, 110, 110, 110]
SHARE_POLYGON_STYLE = {
    "strokeColor": "#1677ff",
    "strokeOpacity": 0.95,
    "strokeWeight": 3,
    "fillColor": "#3ba7ff",
    "fillOpacity": 0.16,
    "zIndex": 20,
}

# 任务清理配置
TASK_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
CLEANUP_INTERVAL_SECONDS = 7 * 24 * 60 * 60


# 错误消息
def read_dotenv() -> dict[str, str]:
    """从项目 .env 文件读取键值对。"""
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


local_env = read_dotenv()
amap_key = os.getenv("VITE_AMAP_KEY") or local_env.get("VITE_AMAP_KEY", "")
amap_security_code = os.getenv("VITE_AMAP_SECURITY_CODE") or local_env.get(
    "VITE_AMAP_SECURITY_CODE",
    "",
)
playwright_executable_path = os.getenv("PLAYWRIGHT_EXECUTABLE_PATH") or ""

# 兼容性别名
port = DEFAULT_PORT
SERVER_RELOAD = False
