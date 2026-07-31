import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from server.api.common import (
    create_snapshot_task,
    get_share_task,
    render_share_page,
    resolve_index_region,
    resolve_index_regions,
    share_page_response,
    submit_snapshot_task,
    task_created_response,
)


def test_create_snapshot_task_owns_shared_task_metadata() -> None:
    context = SimpleNamespace(
        task_store={},
        generate_task_id=lambda: "task-id",
    )

    task = create_snapshot_task(
        context,
        "http://example.test",
        task_type="city",
        share_path="city-share",
        value_label="状态",
        callback_url="",
        data={"city": {}, "districts": []},
    )

    assert task["taskId"] == "task-id"
    assert task["taskType"] == "city"
    assert task["status"] == "processing"
    assert task["mapUrl"] == "http://example.test/api/v1/city-share?taskId=task-id"
    assert task["city"] == {}
    assert task["districts"] == []
    assert context.task_store == {"task-id": task}
    assert task_created_response(task) == {
        "success": True,
        "data": {
            "taskId": "task-id",
            "status": "processing",
            "valueLabel": "状态",
        },
    }


def test_submit_snapshot_task_creates_schedules_and_returns_response() -> None:
    context = SimpleNamespace(
        task_store={},
        generate_task_id=lambda: "task-id",
    )
    scheduled: list[dict[str, object]] = []

    async def prepare(_task: dict[str, object], _context: object) -> bool:
        return True

    response = submit_snapshot_task(
        context,
        "http://example.test",
        task_type="national",
        share_path="map-share",
        value_label="状态",
        callback_url="",
        data={"regions": []},
        prepare=prepare,
        schedule=lambda **options: scheduled.append(options),
    )

    assert response == {
        "success": True,
        "data": {
            "taskId": "task-id",
            "status": "processing",
            "valueLabel": "状态",
        },
    }
    assert scheduled == [
        {
            "task_id": "task-id",
            "origin": "http://example.test",
            "context": context,
            "prepare": prepare,
        }
    ]


def test_get_share_task_uses_persisted_loader_and_preparer() -> None:
    persisted = {"taskId": "task-id", "regions": []}
    prepared: list[dict[str, object]] = []

    async def prepare(task: dict[str, object], _context: object) -> bool:
        prepared.append(task)
        return True

    async def load(_task_id: str) -> dict[str, object]:
        return persisted

    context = SimpleNamespace(task_store={})

    task = asyncio.run(
        get_share_task(
            "task-id",
            context,
            prepare=prepare,
            load=load,
        )
    )

    assert task is persisted
    assert prepared == [persisted]


def test_get_share_task_raises_for_missing_task() -> None:
    context = SimpleNamespace(task_store={})

    async def prepare(_task: dict[str, object], _context: object) -> bool:
        return True

    async def load(_task_id: str) -> None:
        return None

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            get_share_task(
                "missing",
                context,
                prepare=prepare,
                load=load,
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "task not found"


def test_index_region_helpers_share_resolution_rules() -> None:
    async def get_region_index() -> dict[str, dict[str, object]]:
        return {
            "byAdcode": {
                "330100": {
                    "name": "杭州市",
                    "adcode": "330100",
                    "level": "city",
                    "center": [120.1, 30.2],
                },
                "330106": {
                    "name": "西湖区",
                    "adcode": "330106",
                    "level": "district",
                    "center": [120.0, 30.3],
                },
            }
        }

    context = SimpleNamespace(
        get_region_index=get_region_index,
        infer_level=lambda adcode: "city" if adcode.endswith("00") else "district",
    )

    parent, failed_parent = asyncio.run(
        resolve_index_region(
            {"name": "", "adcode": "330100"},
            context,
            missing_reason="city not found",
            level="city",
        )
    )
    children, failed_children = asyncio.run(
        resolve_index_regions(
            [
                {"name": "", "adcode": "330106", "value": "已覆盖"},
                {"name": "不存在", "adcode": "999999", "value": ""},
            ],
            context,
            missing_reason="district not found",
        )
    )

    assert parent == {
        "name": "杭州市",
        "adcode": "330100",
        "level": "city",
        "center": [120.1, 30.2],
    }
    assert failed_parent == []
    assert children == [
        {
            "name": "西湖区",
            "adcode": "330106",
            "level": "district",
            "value": "已覆盖",
            "center": [120.0, 30.3],
        }
    ]
    assert failed_children == [{"name": "不存在", "reason": "district not found"}]


def test_render_share_page_builds_shared_template_context() -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    task = {
        "taskId": "task-id",
        "valueLabel": "结果",
        "city": {"name": "杭州市"},
        "districts": [{"name": "西湖区"}],
    }

    async def render(template: str, data: dict[str, object]) -> str:
        calls.append((template, data))
        return "<html>"

    html = asyncio.run(
        render_share_page(
            "city_share.html",
            task,
            "city",
            "districts",
            render=render,
        )
    )

    assert html == "<html>"
    assert calls == [
        (
            "city_share.html",
            {
                "taskId": "task-id",
                "valueLabel": "结果",
                "city": {"name": "杭州市"},
                "districts": [{"name": "西湖区"}],
            },
        )
    ]


def test_share_page_response_reuses_task_lookup_and_rendering() -> None:
    task = {
        "taskId": "task-id",
        "valueLabel": "状态",
        "regions": [],
    }
    context = SimpleNamespace(task_store={"task-id": task})

    async def prepare(_task: dict[str, object], _context: object) -> bool:
        return True

    async def render(_template: str, _data: dict[str, object]) -> str:
        return "<html>map</html>"

    response = asyncio.run(
        share_page_response(
            "task-id",
            context,
            prepare=prepare,
            template_name="national_share.html",
            region_keys=("regions",),
            render=render,
        )
    )

    assert response.status_code == 200
    assert response.body == b"<html>map</html>"
