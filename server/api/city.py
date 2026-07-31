"""市级地图截图接口。"""

# ruff: noqa: F403, F405

from __future__ import annotations

from server import *  # noqa: F403
from server.api.common import (
    enrich_scope,
    resolve_index_region,
    resolve_index_regions,
    share_page_response,
    submit_snapshot_task,
)


async def _prepare_persisted_city_task(
    task: dict[str, Any], ctx: SnapshotContext
) -> bool:
    """验证并补全持久化市级任务。"""

    districts = task.get("districts")
    if not isinstance(districts, list):
        return False
    if not isinstance(task.get("city"), dict):
        return False
    await enrich_scope(
        task,
        ctx,
        parent_key="city",
        children_key="districts",
        parent_level="city",
    )
    return True


async def _prepare_city_task(
    task: dict[str, Any],
    ctx: SnapshotContext,
) -> bool:
    """解析市和区县并写回任务。"""

    city, city_failed = await resolve_index_region(
        task["requestedCity"],
        ctx,
        missing_reason="city not found",
        level="city",
    )
    districts, district_failed = await resolve_index_regions(
        task["requestedDistricts"],
        ctx,
        missing_reason="district not found",
    )
    task["city"] = city or {}
    task["districts"] = districts
    task["failedDistricts"] = [*city_failed, *district_failed]
    return bool(city and districts and not task["failedDistricts"])


def register_city_snapshot_routes(router: APIRouter, ctx: SnapshotContext) -> None:
    """向主应用注册市级截图相关路由。"""

    @router.get("/city-share", summary="市级地图渲染页")
    async def city_share(params: CityShareQuery = Depends()):
        return await share_page_response(
            params.taskId,
            ctx,
            prepare=_prepare_persisted_city_task,
            template_name="city_share.html",
            region_keys=("city", "districts"),
        )

    @router.post("/city-snapshot", summary="创建市级地图截图任务")
    async def city_snapshot_create(
        request: FastAPIRequest,
        body: CitySnapshotCreateRequest,
    ):
        """创建市级地图截图任务，传入 city + districts，callback_url选填，会返回taskId"""

        origin = ctx.get_origin(request)
        return submit_snapshot_task(
            ctx,
            origin,
            task_type="city",
            share_path="city-share",
            value_label=body.value_label,
            callback_url=body.callback_url,
            data={
                "requestedCity": body.city.model_dump(),
                "requestedDistricts": [
                    district.model_dump() for district in body.districts
                ],
                "city": {},
                "districts": [],
                "failedDistricts": [],
            },
            prepare=_prepare_city_task,
        )
