import asyncio

from server.services import tasks
from server.services.tasks import build_callback_payload, serialize_public_task


def test_task_storage_supports_async_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tasks, "SNAPSHOT_DIR", tmp_path)
    task = {
        "taskId": "stored-task",
        "status": "processing",
        "createdAt": 1,
    }

    asyncio.run(tasks.persist_task(task))

    assert asyncio.run(tasks.load_task("stored-task")) == task


def test_task_cleanup_removes_expired_files_asynchronously(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(tasks, "SNAPSHOT_DIR", tmp_path)
    task_store = {
        "expired-task": {
            "taskId": "expired-task",
            "status": "done",
            "createdAt": 0,
        }
    }
    image_path = tmp_path / "expired-task.png"
    result_path = tmp_path / "expired-task.json"
    image_path.write_bytes(b"png")
    result_path.write_text("{}", encoding="utf-8")

    removed = asyncio.run(tasks.cleanup_expired_tasks(task_store))

    assert removed == 1
    assert task_store == {}
    assert not image_path.exists()
    assert not result_path.exists()


def test_serialize_public_city_task_uses_district_fields() -> None:
    task = {
        "taskId": "city-task",
        "taskType": "city",
        "status": "done",
        "valueLabel": "状态",
        "imageUrl": "http://example.test/city.png",
        "mapUrl": "http://example.test/city-share",
        "city": {"name": "杭州市", "adcode": "330100"},
        "districts": [
            {
                "name": "西湖区",
                "adcode": "330106",
                "level": "district",
                "value": "已覆盖",
                "center": [120.1, 30.2],
            }
        ],
    }

    assert serialize_public_task(task) == {
        "taskId": "city-task",
        "status": "done",
        "valueLabel": "状态",
        "imageUrl": "http://example.test/city.png",
        "mapUrl": "http://example.test/city-share",
        "city": {"name": "杭州市", "adcode": "330100"},
        "districts": [{"name": "西湖区", "adcode": "330106", "value": "已覆盖"}],
    }


def test_build_callback_payload_keeps_national_levels_and_failures() -> None:
    task = {
        "taskId": "national-task",
        "taskType": "national",
        "status": "done",
        "valueLabel": "结果",
        "imageUrl": "http://example.test/national.png",
        "mapUrl": "http://example.test/map-share",
        "regions": [
            {
                "name": "杭州市",
                "adcode": "330100",
                "level": "city",
                "value": "8",
            }
        ],
        "failedRegions": [{"name": "不存在", "reason": "region not found"}],
    }

    assert build_callback_payload(task) == {
        "taskId": "national-task",
        "status": "done",
        "valueLabel": "结果",
        "imageUrl": "http://example.test/national.png",
        "mapUrl": "http://example.test/map-share",
        "regions": [
            {
                "name": "杭州市",
                "adcode": "330100",
                "level": "city",
                "value": "8",
            }
        ],
        "failedRegions": [{"name": "不存在", "reason": "region not found"}],
    }


def test_serialize_processing_task_has_stable_minimal_shape() -> None:
    assert serialize_public_task(
        {
            "taskId": "pending-task",
            "taskType": "province",
            "status": "processing",
            "valueLabel": "状态",
        }
    ) == {
        "taskId": "pending-task",
        "status": "processing",
        "valueLabel": "状态",
    }
