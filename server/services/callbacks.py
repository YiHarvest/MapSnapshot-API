"""HTTP 回调发送。"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.request import Request, urlopen

from server.services.tasks import build_callback_payload


async def send_callback(task: dict[str, Any], origin: str) -> None:
    """当回调 URL 存在时，POST 回调响应体。"""

    callback_url = task.get("callbackUrl")
    if not callback_url:
        return

    data = json.dumps(build_callback_payload(task), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Map-Snapshot-Task-Id": task["taskId"],
        "X-Map-Snapshot-Origin": origin,
    }

    def post() -> None:
        """在后台线程中执行 POST 请求。"""
        request = Request(callback_url, data=data, headers=headers, method="POST")
        with urlopen(request, timeout=30) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"callback request failed: {response.status}")

    try:
        await asyncio.to_thread(post)
    except Exception as exc:
        raise RuntimeError(f"callback request failed: {exc}") from exc
