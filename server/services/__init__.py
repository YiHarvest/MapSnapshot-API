"""可复用的应用服务模块。"""

from server.services.callbacks import send_callback
from server.services.execution import (
    ExecutionContext,
    execute_snapshot_task,
    run_background_task,
    schedule_background_task,
    schedule_snapshot_task,
    send_callback_safely,
)
from server.services.geojson import RegionService, build_region_index
from server.services.naming import (
    choose_display_name,
    infer_level,
    looks_mojibake,
    normalize_text,
)
from server.services.screenshots import capture_share_page
from server.services.tasks import (
    build_callback_payload,
    cleanup_expired_tasks,
    generate_task_id,
    get_origin,
    load_task,
    persist_task,
    safe_task_path,
    serialize_public_task,
)
from server.services.templates import render_share_template

__all__ = [
    "ExecutionContext",
    "RegionService",
    "build_callback_payload",
    "build_region_index",
    "capture_share_page",
    "choose_display_name",
    "cleanup_expired_tasks",
    "execute_snapshot_task",
    "generate_task_id",
    "get_origin",
    "infer_level",
    "load_task",
    "looks_mojibake",
    "normalize_text",
    "persist_task",
    "render_share_template",
    "run_background_task",
    "safe_task_path",
    "schedule_background_task",
    "schedule_snapshot_task",
    "send_callback",
    "send_callback_safely",
    "serialize_public_task",
]
