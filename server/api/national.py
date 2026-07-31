"""全国地图截图接口。"""

# ruff: noqa: F403, F405

from __future__ import annotations

from server import *  # noqa: F403
from server.api.common import (
    enrich_region_record,
    share_page_response,
    submit_snapshot_task,
)


async def _prepare_persisted_national_task(
    task: dict[str, Any], ctx: SnapshotContext
) -> bool:
    """验证并补全持久化全国任务。"""

    regions = task.get("regions")
    if not isinstance(regions, list):
        return False

    index = await ctx.get_region_index()
    enriched_regions: list[dict[str, Any]] = []
    for region in regions:
        if not isinstance(region, dict):
            continue
        adcode = str(region.get("adcode") or "").strip()
        if not adcode:
            continue
        if not enrich_region_record(region, index, ctx.infer_level):
            region.update(
                name=normalize_text(region.get("name")) or adcode,
                level=region.get("level") or ctx.infer_level(adcode),
            )
        region["value"] = normalize_text(region.get("value"))
        enriched_regions.append(region)

    task["regions"] = enriched_regions
    return bool(enriched_regions)


async def _prepare_national_task(
    task: dict[str, Any],
    ctx: SnapshotContext,
) -> bool:
    """解析全国行政区并写回任务。"""

    resolved, failed_regions = await ctx.resolve_regions(task["requestedRegions"])
    task["regions"] = resolved
    task["failedRegions"] = failed_regions
    return bool(resolved and not failed_regions)


def register_national_snapshot_routes(router: APIRouter, ctx: SnapshotContext) -> None:
    """向主应用注册全国截图相关路由。"""

    @router.get("/map-share", summary="全国地图渲染页")
    async def map_share(params: NationShareQuery = Depends()):
        return await share_page_response(
            params.taskId,
            ctx,
            prepare=_prepare_persisted_national_task,
            template_name="national_share.html",
            region_keys=("regions",),
        )

    @router.post("/snapshot", summary="创建全国地图截图任务")
    async def national_snapshot_create(
        request: FastAPIRequest,
        body: NationSnapshotCreateRequest,
    ):
        """创建全国地图截图任务，传入 regions，callback_url选填，会返回taskId"""

        origin = ctx.get_origin(request)
        return submit_snapshot_task(
            ctx,
            origin,
            task_type="national",
            share_path="map-share",
            value_label=body.value_label or "状态",
            callback_url=body.callback_url,
            data={
                "requestedRegions": [region.model_dump() for region in body.regions],
                "regions": [],
                "failedRegions": [],
            },
            prepare=_prepare_national_task,
        )
