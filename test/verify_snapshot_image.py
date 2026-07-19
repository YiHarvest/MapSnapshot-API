#!/usr/bin/env python3
"""验证截图图片是否可正常解码的测试脚本。

用法: python test/verify_snapshot_image.py <image-url>
"""

from __future__ import annotations

import sys
import struct
import urllib.request
import zlib
from typing import Tuple


def usage() -> None:
    """打印用法提示到 stderr。"""
    print("Usage: python test/verify_snapshot_image.py <image-url>", file=sys.stderr)


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

    # 只要能正常解压，说明 PNG 图像数据块可被解码
    zlib.decompress(compressed)

    return width, height


def main() -> None:
    """验证 PNG 截图图片的主入口函数。

    通过 HTTP 下载图片后进行格式校验、Content-Type 校验和 PNG 解码校验。
    """
    if len(sys.argv) < 2:
        usage()
        raise SystemExit(1)

    image_url = sys.argv[1]

    try:
        with urllib.request.urlopen(image_url) as response:
            status = response.getcode()
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
    except Exception as exc:
        fail(f"request failed: {exc}")

    if status != 200:
        fail(f"unexpected status code: {status}")
    pass_msg("status code = 200")

    if not content_type.lower().startswith("image/png"):
        fail(f"unexpected content-type: {content_type or '(empty)'}")
    pass_msg(f"content-type = {content_type}")

    try:
        width, height = parse_png(body)
        pass_msg(f"png decode ok: {width}x{height}")
    except Exception as exc:
        fail(f"png decode failed: {exc}")

    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
