"""截图服务配置模块。

定义所有可调参数，包括路径、端口、截图参数、GeoJSON 样式和错误消息。
"""

from __future__ import annotations

import os
from pathlib import Path

# ============================================================
# 路径常量
# ============================================================

ROOT_DIR = Path(__file__).resolve().parent.parent
"""项目根目录"""

PUBLIC_DIR = ROOT_DIR / "public"
"""前端静态资源目录"""

SNAPSHOT_DIR = PUBLIC_DIR / "snapshots"
"""截图输出目录"""

DEFAULT_PORT = int(os.getenv("MAP_SNAPSHOT_PORT") or os.getenv("PORT") or "28787")
"""服务监听端口，可通过环境变量 MAP_SNAPSHOT_PORT 或 PORT 覆盖"""

SERVER_RELOAD = os.getenv("MAP_SNAPSHOT_RELOAD", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
"""开发服务热重载开关，默认开启；生产环境可设置 MAP_SNAPSHOT_RELOAD=0 关闭"""

BASE_URL = os.getenv("SNAPSHOT_BASE_URL", "").rstrip("/")
"""nginx 反向代理前缀，如 /feisu/snapshot；不设置则为空字符串"""

# ============================================================
# 浏览器配置
# ============================================================

EDGE_EXECUTABLE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
"""Edge 浏览器可执行文件搜索路径列表（按优先级排序）"""

VIEWPORT = {"width": 1280, "height": 820}
"""浏览器视口尺寸（宽 x 高）"""

DEVICE_SCALE_FACTOR = 1
"""设备像素比（1 = 普通，2 = Retina）"""

SCREENSHOT_CONCURRENCY = 2
"""最大并行截图数，超出排队等待"""

# ============================================================
# 截图超时参数
# ============================================================

MAP_READY_TIMEOUT_MS = 30000
"""等待地图渲染完成的超时时间（毫秒）"""

SCREENSHOT_DELAY_MS = 1200
"""地图 ready 后额外等待时间（毫秒），确保瓦片完全加载"""

MAP_READY_FALLBACK_TIMEOUT_MS = 10000
"""地图 ready 兜底超时（毫秒），防止 complete 事件不触发"""

MAP_COMPLETE_DELAY_MS = 5000
"""地图 complete 事件后的等待时间（毫秒）"""

# ============================================================
# 地图分享页参数
# ============================================================

SHARE_MAP_ZOOM = 7
"""地图分享页默认缩放级别"""

SHARE_MAP_ZOOMS = [3, 18]
"""地图分享页缩放范围 [最小, 最大]"""

SINGLE_REGION_ZOOM = {
    "province": 6,
    "city": 9,
    "district": 10,
}
"""单区域截图时的自适应缩放级别（按层级区分）"""

SINGLE_REGION_DEFAULT_ZOOM = 10
"""单区域默认缩放（无法识别层级时使用）"""

MULTI_FITVIEW_PADDING = [70, 70, 70, 70]
"""多区域 fitView 内边距 [上, 右, 下, 左]"""

SINGLE_FITVIEW_PADDING = [110, 110, 110, 110]
"""单区域 fitView 内边距 [上, 右, 下, 左]"""

# ============================================================
# 多边形样式（地图分享页用）
# ============================================================

SHARE_POLYGON_STYLE = {
    "strokeColor": "#1677ff",
    "strokeOpacity": 0.95,
    "strokeWeight": 3,
    "fillColor": "#3ba7ff",
    "fillOpacity": 0.16,
    "zIndex": 20,
}
"""行政区划边界多边形样式（蓝色描边 + 半透明填充）"""

# ============================================================
# 任务清理
# ============================================================

TASK_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
"""任务保留时长（秒），默认 1 周"""

CLEANUP_INTERVAL_SECONDS = 7 * 24 * 60 * 60
"""清理检查间隔（秒），默认 1 周"""

# ============================================================
# 错误消息
# ============================================================

ERROR_MSG = {
    "MISSING_AMAP_KEY": "missing VITE_AMAP_KEY",
    "REGIONS_NOT_FOUND": "some regions could not be resolved",
    "TASK_EXECUTION_FAILED": "task execution failed",
    "SCREENSHOT_FAILED": "screenshot failed",
    "CALLBACK_FAILED": "callback request failed",
    "TASK_NOT_FOUND": "task not found",
    "IMAGE_NOT_FOUND": "image not found",
    "INVALID_JSON": "invalid JSON body",
    "NOT_FOUND": "Not Found",
}
"""统一错误消息字典"""

REGION_NOT_FOUND_REASON = "region not found"
"""区域匹配失败时的原因说明"""

UNKNOWN_REGION_NAME = "unknown region"
"""无法识别区域时的回退名称"""


def read_dotenv() -> dict[str, str]:
    """从项目根目录的 .env 文件中读取环境变量。

    解析 KEY=VALUE 格式的行，自动跳过注释和空行。
    值两侧的引号会被移除。

    Returns:
        dict[str, str]: 环境变量键值对字典，文件不存在时返回空字典
    """
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
    "VITE_AMAP_SECURITY_CODE", ""
)
port = DEFAULT_PORT
playwright_executable_path = os.getenv("PLAYWRIGHT_EXECUTABLE_PATH") or ""
