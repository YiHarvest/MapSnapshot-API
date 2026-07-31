"""HTTP 路由注册模块。"""

from server.api.city import register_city_snapshot_routes
from server.api.common import (
    create_snapshot_task,
    enrich_region_record,
    enrich_scope,
    get_share_task,
    render_share_page,
    resolve_index_region,
    resolve_index_regions,
    share_page_response,
    submit_snapshot_task,
    task_created_response,
)
from server.api.errors import register_exception_handlers
from server.api.national import register_national_snapshot_routes
from server.api.province import register_province_snapshot_routes
from server.api.system import register_system_routes

__all__ = [
    "register_city_snapshot_routes",
    "register_exception_handlers",
    "register_national_snapshot_routes",
    "register_province_snapshot_routes",
    "register_system_routes",
    "create_snapshot_task",
    "enrich_region_record",
    "enrich_scope",
    "get_share_task",
    "render_share_page",
    "resolve_index_region",
    "resolve_index_regions",
    "share_page_response",
    "submit_snapshot_task",
    "task_created_response",
]
