"""Real browser smoke tests for all public snapshot modes."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import pytest

BASE_URL = os.getenv("SNAPSHOT_TEST_BASE_URL", "http://127.0.0.1:28787").rstrip("/")

CASES: list[tuple[str, dict[str, Any]]] = [
    (
        "/api/v1/snapshot",
        {
            "regions": [
                {"name": "浙江省", "adcode": "330000", "value": "已覆盖"},
                {"name": "杭州市", "adcode": "330100", "value": "处理中"},
            ],
            "value_label": "状态",
        },
    ),
    (
        "/api/v1/province-snapshot",
        {
            "province": {"name": "浙江省", "adcode": "330000"},
            "regions": [
                {"name": "杭州市", "adcode": "330100", "value": "已覆盖"},
                {"name": "温州市", "adcode": "330300", "value": "处理中"},
            ],
            "value_label": "状态",
        },
    ),
    (
        "/api/v1/city-snapshot",
        {
            "city": {"name": "杭州市", "adcode": "330100"},
            "districts": [
                {"name": "西湖区", "adcode": "330106", "value": "已覆盖"},
                {"name": "余杭区", "adcode": "330110", "value": "处理中"},
            ],
            "value_label": "状态",
        },
    ),
]


@pytest.mark.e2e
@pytest.mark.parametrize(("path", "payload"), CASES)
def test_snapshot_mode_generates_png(
    path: str,
    payload: dict[str, Any],
) -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        create_response = client.post(path, json=payload)
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["success"] is True
        task_id = created["data"]["taskId"]
        assert created["data"]["status"] == "processing"

        deadline = time.monotonic() + 180
        result: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            query_response = client.get(f"/api/v1/snapshot/{task_id}")
            body = query_response.json()
            if body.get("data", {}).get("status") in {"done", "failed"}:
                result = body
                break
            time.sleep(0.5)

        assert result is not None, f"task {task_id} did not finish"
        assert result["success"] is True, result
        assert result["data"]["status"] == "done"

        image_response = client.get(result["data"]["imageUrl"])
        assert image_response.status_code == 200
        assert image_response.headers["content-type"].startswith("image/png")
        assert image_response.content.startswith(b"\x89PNG\r\n\x1a\n")
