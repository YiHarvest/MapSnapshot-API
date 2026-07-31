import pytest

from server.services.naming import choose_display_name, infer_level, normalize_text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (" 330100 ", "330100"),
        (8, "8"),
    ],
)
def test_normalize_text_returns_trimmed_string(value: object, expected: str) -> None:
    assert normalize_text(value) == expected


@pytest.mark.parametrize(
    ("adcode", "expected"),
    [
        ("330000", "province"),
        ("330100", "city"),
        ("330106", "district"),
        ("", "province"),
    ],
)
def test_infer_level_uses_adcode_suffix(adcode: str, expected: str) -> None:
    assert infer_level(adcode) == expected


def test_choose_display_name_prefers_readable_requested_name() -> None:
    assert choose_display_name(" 杭州市 ", "杭州", "330100") == "杭州市"


def test_choose_display_name_replaces_mojibake_with_index_name() -> None:
    assert choose_display_name("???", "杭州市", "330100") == "杭州市"


def test_choose_display_name_falls_back_to_adcode() -> None:
    assert choose_display_name("", "�", "330100") == "330100"
