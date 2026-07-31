import pytest
from pydantic import ValidationError

from server.model import (
    CitySnapshotCreateRequest,
    NationSnapshotCreateRequest,
    ProvinceSnapshotCreateRequest,
)


def test_national_schema_trims_request_strings() -> None:
    request = NationSnapshotCreateRequest.model_validate(
        {
            "regions": [{"name": " 杭州市 ", "adcode": " 330100 ", "value": " 8 "}],
            "value_label": " 状态 ",
            "callback_url": " https://example.test/callback ",
        }
    )

    assert request.regions[0].model_dump() == {
        "name": "杭州市",
        "adcode": "330100",
        "value": "8",
    }
    assert request.value_label == "状态"
    assert request.callback_url == "https://example.test/callback"


def test_province_schema_preserves_nested_contract() -> None:
    request = ProvinceSnapshotCreateRequest.model_validate(
        {
            "province": {"name": " 浙江省 ", "adcode": " 330000 "},
            "regions": [{"name": " 杭州市 ", "adcode": " 330100 ", "value": " A "}],
        }
    )

    assert request.province.adcode == "330000"
    assert request.regions[0].value == "A"
    assert request.value_label == "状态"


def test_city_schema_preserves_nested_contract() -> None:
    request = CitySnapshotCreateRequest.model_validate(
        {
            "city": {"name": " 杭州市 ", "adcode": " 330100 "},
            "districts": [
                {"name": " 西湖区 ", "adcode": " 330106 ", "value": " 已覆盖 "}
            ],
        }
    )

    assert request.city.name == "杭州市"
    assert request.districts[0].adcode == "330106"
    assert request.districts[0].value == "已覆盖"


def test_city_schema_rejects_city_level_district_adcode() -> None:
    with pytest.raises(ValidationError, match="district adcode must not end with '00'"):
        CitySnapshotCreateRequest.model_validate(
            {
                "city": {"name": "杭州市", "adcode": "330100"},
                "districts": [{"name": "错误区域", "adcode": "330200"}],
            }
        )


def test_city_schema_rejects_empty_districts() -> None:
    with pytest.raises(ValidationError, match="districts must not be empty"):
        CitySnapshotCreateRequest.model_validate(
            {
                "city": {"name": "杭州市", "adcode": "330100"},
                "districts": [],
            }
        )


def test_snapshot_schema_rejects_invalid_callback_url() -> None:
    with pytest.raises(ValidationError, match="callback_url must be an HTTP URL"):
        ProvinceSnapshotCreateRequest.model_validate(
            {
                "province": {"adcode": "330000"},
                "regions": [{"adcode": "330100"}],
                "callback_url": "javascript:alert(1)",
            }
        )
