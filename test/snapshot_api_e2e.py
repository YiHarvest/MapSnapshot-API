#!/usr/bin/env python3
"""地图标记截图接口端到端测试脚本。

测试流程：
1. 启动本地回调 HTTP 服务器
2. 调用截图 API 创建任务
3. 等待服务端截图完成后回调到本地
4. 验证回调数据并解码截图 PNG
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import threading
import urllib.error
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Tuple

DEFAULT_BASE_URL = "http://127.0.0.1:8787"
"""默认截图服务地址"""

DEFAULT_CALLBACK_HOST = "127.0.0.1"
"""默认回调服务器监听地址"""

DEFAULT_CALLBACK_PORT = 8899
"""默认回调服务器监听端口"""

DEFAULT_TIMEOUT_SECONDS = 180.0
"""默认总超时时间（秒）"""


def usage() -> None:
    """打印用法提示到 stderr。"""
    print(
        "Usage: python test/snapshot_api_e2e.py [--base-url URL] [--callback-port PORT] [--timeout SECONDS]",
        file=sys.stderr,
    )


def fail(message: str) -> None:
    """打印失败消息并退出程序。

    Args:
        message: 失败原因描述
    """
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def pass_msg(message: str) -> None:
    """打印通过消息。

    Args:
        message: 通过验证的描述
    """
    print(f"PASS: {message}")


def read_u32_be(data: bytes, offset: int) -> int:
    """从字节数据中按大端序读取 32 位无符号整数。

    Args:
        data: 原始字节数据
        offset: 读取起始偏移量

    Returns:
        解析后的 uint32 值
    """
    return struct.unpack_from(">I", data, offset)[0]


def parse_png(data: bytes) -> Tuple[int, int]:
    """解析 PNG 二进制数据，验证合法性并返回尺寸。

    逐块解析 IHDR / IDAT / IEND chunk，并将所有 IDAT 数据
    合并后尝试 zlib 解压以验证图像数据完整性。

    Args:
        data: PNG 文件的原始字节数据

    Returns:
        (width, height): 图像宽高（像素）

    Raises:
        ValueError: PNG 格式非法或解码失败
    """
    signature = b"\x89PNG\r\n\x1a\n"
    if len(data) < len(signature) or data[:8] != signature:
        raise ValueError("invalid PNG signature")

    offset = 8
    width = 0
    height = 0
    saw_ihdr = False
    saw_iend = False
    idat_parts: list[bytes] = []

    while offset + 12 <= len(data):
        length = read_u32_be(data, offset)
        offset += 4

        chunk_type = data[offset : offset + 4].decode("ascii", errors="replace")
        offset += 4

        if offset + length + 4 > len(data):
            raise ValueError(f"truncated PNG chunk: {chunk_type}")

        chunk_data = data[offset : offset + length]
        offset += length
        offset += 4  # CRC

        if chunk_type == "IHDR":
            if length != 13:
                raise ValueError("invalid IHDR length")
            width = read_u32_be(chunk_data, 0)
            height = read_u32_be(chunk_data, 4)
            saw_ihdr = True
        elif chunk_type == "IDAT":
            idat_parts.append(chunk_data)
        elif chunk_type == "IEND":
            saw_iend = True
            break

    if not saw_ihdr:
        raise ValueError("IHDR chunk not found")
    if not saw_iend:
        raise ValueError("IEND chunk not found")
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid PNG dimensions: {width}x{height}")

    compressed = b"".join(idat_parts)
    if not compressed:
        raise ValueError("IDAT data is empty")

    zlib.decompress(compressed)
    return width, height


def http_json(
    url: str, payload: dict[str, Any], timeout: float = 30.0
) -> tuple[int, dict[str, Any]]:
    """发送 POST JSON 请求并返回 (状态码, 响应 JSON)。

    Args:
        url: 请求地址
        payload: JSON 请求体字典
        timeout: 请求超时时间（秒）

    Returns:
        (http_status, parsed_json): HTTP 状态码和解析后的 JSON 对象
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.getcode(), json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"HTTP {exc.code} calling {url}: {body}")
    except Exception as exc:
        fail(f"request failed: {exc}")


def http_bytes(url: str, timeout: float = 30.0) -> tuple[int, str, bytes]:
    """发送 GET 请求并返回 (状态码, Content-Type, 响应体)。

    Args:
        url: 请求地址
        timeout: 请求超时时间（秒）

    Returns:
        (status_code, content_type, body_bytes): 三元组
    """
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
            return status, content_type, body
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, exc.headers.get("Content-Type", ""), body
    except Exception as exc:
        fail(f"request failed: {exc}")


def verify_image(image_url: str) -> None:
    """验证截图图片的完整性和格式。

    校验步骤：
    1. HTTP 状态码必须为 200
    2. Content-Type 必须为 image/png
    3. PNG 二进制数据必须能正常解码

    Args:
        image_url: 截图图片 URL
    """
    status, content_type, body = http_bytes(image_url)
    if status != 200:
        fail(f"unexpected image status code: {status}")
    pass_msg("image status code = 200")

    if not content_type.lower().startswith("image/png"):
        fail(f"unexpected image content-type: {content_type or '(empty)'}")
    pass_msg(f"image content-type = {content_type}")

    try:
        width, height = parse_png(body)
    except Exception as exc:
        fail(f"png decode failed: {exc}")
    pass_msg(f"png decode ok: {width}x{height}")


class CallbackState:
    """回调服务器状态容器。

    用于存储回调接收到的数据和线程同步事件。
    """

    def __init__(self) -> None:
        self.event = threading.Event()
        """收到回调时触发的事件"""

        self.payload: dict[str, Any] | None = None
        """回调请求的 JSON 数据"""

        self.request_path: str | None = None
        """回调请求的路径"""

        self.status_code: int | None = None
        """回调处理的 HTTP 状态码"""


def make_handler(state: CallbackState):
    """创建回调 HTTP 请求处理器。

    Args:
        state: 共享回调状态实例

    Returns:
        CallbackHandler: 配置好的 HTTP 请求处理器类
    """

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            """处理 POST 回调请求。

            解析 JSON 请求体，存储到共享状态中。
            成功后返回 {"success": true}。
            """
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"

            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"success":false,"message":"invalid callback json"}')
                state.status_code = 400
                return

            state.payload = payload
            state.request_path = self.path
            state.status_code = 200
            state.event.set()

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"success":true}')

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            """屏蔽默认请求日志输出。"""
            return

    return CallbackHandler


def start_callback_server(
    host: str, port: int, state: CallbackState
) -> ThreadingHTTPServer:
    """启动本地回调 HTTP 服务器（后台线程）。

    Args:
        host: 监听地址
        port: 监听端口
        state: 共享回调状态实例

    Returns:
        ThreadingHTTPServer: 已启动的服务器实例
    """
    handler = make_handler(state)

    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        fail(f"cannot bind callback server on {host}:{port}: {exc}")

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def create_task(base_url: str, payload: dict[str, Any]) -> str:
    """调用截图 API 创建任务。

    Args:
        base_url: 截图服务基础 URL
        payload: 请求体字典

    Returns:
        创建成功返回的 taskId
    """
    url = f"{base_url}/api/map-marker-snapshot"
    status, result = http_json(url, payload)

    if status != 200 or not isinstance(result, dict) or not result.get("success"):
        fail(f"unexpected create response: {result}")

    data = result.get("data") or {}
    task_id = data.get("taskId")
    task_status = data.get("status")
    if not task_id or task_status != "processing":
        fail(f"unexpected create payload: {result}")

    pass_msg(f"created taskId = {task_id}")
    return str(task_id)


def wait_for_callback(state: CallbackState, timeout_seconds: float) -> dict[str, Any]:
    """阻塞等待回调到达。

    Args:
        state: 共享回调状态实例
        timeout_seconds: 超时时间（秒）

    Returns:
        回调请求的 JSON 数据
    """
    if not state.event.wait(timeout_seconds):
        fail("timeout waiting for callback_url POST")
    if state.status_code != 200:
        fail(f"unexpected callback handler status: {state.status_code}")
    if not isinstance(state.payload, dict):
        fail("callback payload missing")
    return state.payload


def main() -> None:
    """端到端测试主入口。

    执行完整测试流水线：
    1. 解析命令行参数
    2. 启动本地回调服务器
    3. 创建截图任务（杭州 + 温州，value = 8）
    4. 等待回调通知
    5. 下载并验证截图 PNG
    """
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--callback-host", default=DEFAULT_CALLBACK_HOST)
    parser.add_argument("--callback-port", type=int, default=DEFAULT_CALLBACK_PORT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()

    state = CallbackState()
    server = start_callback_server(args.callback_host, args.callback_port, state)
    callback_url = f"http://{args.callback_host}:{args.callback_port}/callback"

    payload = {
        "regions": [
            {"name": "杭州市", "adcode": "330100"},
            {"name": "温州市", "adcode": "330300"},
        ],
        "value": "8",
        "callback_url": callback_url,
    }

    print(f"Listening callback_url at {callback_url}")
    print(f"POST {args.base_url}/api/map-marker-snapshot")
    task_id = create_task(args.base_url, payload)

    callback_payload = wait_for_callback(state, args.timeout)
    pass_msg(f"callback received on {state.request_path}")

    if callback_payload.get("taskId") != task_id:
        fail(f"callback taskId mismatch: {callback_payload}")

    if callback_payload.get("status") != "done":
        fail(f"unexpected callback status: {callback_payload}")

    image_url = callback_payload.get("imageUrl")
    map_url = callback_payload.get("mapUrl")

    if not image_url:
        fail(f"missing imageUrl in callback payload: {callback_payload}")

    pass_msg(f"imageUrl = {image_url}")
    if map_url:
        pass_msg(f"mapUrl = {map_url}")

    verify_image(str(image_url))

    server.shutdown()
    server.server_close()

    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
