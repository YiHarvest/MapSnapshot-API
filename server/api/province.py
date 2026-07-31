"""省级地图截图接口。"""

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


async def _prepare_persisted_province_task(
    task: dict[str, Any], ctx: SnapshotContext
) -> bool:
    """验证并补全持久化省级任务。"""

    regions = task.get("regions")
    if not isinstance(regions, list):
        return False

    province = task.get("province")
    if not isinstance(province, dict):
        province = _infer_province_from_regions(regions)
        if not province:
            return False
        task["province"] = province

    await enrich_scope(
        task,
        ctx,
        parent_key="province",
        children_key="regions",
    )
    return True


def _infer_province_from_regions(regions: list[Any]) -> dict[str, str] | None:
    """从子区域列表里反推 province 的省/市 adcode。"""

    adcodes = [
        str(region.get("adcode") or "").strip()
        for region in regions
        if isinstance(region, dict)
    ]
    adcodes = [adcode for adcode in adcodes if len(adcode) >= 6]
    if not adcodes:
        return None

    first = adcodes[0]
    if all(adcode[:4] == first[:4] for adcode in adcodes):
        adcode = first[:4] + "00"
        return {"name": adcode, "adcode": adcode, "level": "city"}
    if all(adcode[:2] == first[:2] for adcode in adcodes):
        adcode = first[:2] + "0000"
        return {"name": adcode, "adcode": adcode, "level": "province"}
    return None


async def _prepare_province_task(
    task: dict[str, Any],
    ctx: SnapshotContext,
) -> bool:
    """解析省级范围并写回任务。"""

    province, province_failed = await resolve_index_region(
        task["requestedProvince"],
        ctx,
        missing_reason="province not found",
    )
    regions, region_failed = await resolve_index_regions(
        task["requestedRegions"],
        ctx,
        missing_reason="region not found",
    )
    task["province"] = province or {}
    task["regions"] = regions
    task["failedRegions"] = [*province_failed, *region_failed]
    return bool(province and regions and not task["failedRegions"])


def register_province_snapshot_routes(router: APIRouter, ctx: SnapshotContext) -> None:
    """向主应用注册省级地图截图相关路由。"""

    @router.get("/province-share", summary="省级地图渲染页")
    async def province_share(params: ProvinceShareQuery = Depends()):
        return await share_page_response(
            params.taskId,
            ctx,
            prepare=_prepare_persisted_province_task,
            template_name="province_share.html",
            region_keys=("province", "regions"),
        )

    @router.post("/province-snapshot", summary="创建省级地图截图任务")
    async def province_snapshot_create(
        request: FastAPIRequest,
        body: ProvinceSnapshotCreateRequest,
    ):
        """创建省级地图截图任务，传入 province + regions，callback_url选填，会返回taskId"""

        origin = ctx.get_origin(request)
        return submit_snapshot_task(
            ctx,
            origin,
            task_type="province",
            share_path="province-share",
            value_label=body.value_label,
            callback_url=body.callback_url,
            data={
                "requestedProvince": body.province.model_dump(),
                "requestedRegions": [region.model_dump() for region in body.regions],
                "province": {},
                "regions": [],
                "failedRegions": [],
            },
            prepare=_prepare_province_task,
        )
