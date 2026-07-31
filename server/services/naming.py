"""行政区划字符串和层级处理工具。"""

from __future__ import annotations

from typing import Any


def normalize_text(value: Any) -> str:
    """将任意值转换为去除首尾空白的字符串。"""

    return str(value or "").strip()


def looks_mojibake(value: Any) -> bool:
    """检查文本是否包含乱码占位符。"""

    text = normalize_text(value)
    return "?" in text or "�" in text


def choose_display_name(
    requested_name: Any,
    matched_name: Any,
    adcode: Any,
) -> str:
    """选择可读的显示名称，优先使用请求名称，其次是索引名称，最后是 adcode。"""

    requested = normalize_text(requested_name)
    code = normalize_text(adcode)
    if requested and requested != code and not looks_mojibake(requested):
        return requested

    matched = normalize_text(matched_name)
    if matched and not looks_mojibake(matched):
        return matched
    return code


def infer_level(adcode: Any) -> str:
    """根据行政区划代码推断层级：省/市/区。"""

    code = normalize_text(adcode)
    if not code or code.endswith("0000"):
        return "province"
    if code.endswith("00"):
        return "city"
    return "district"
