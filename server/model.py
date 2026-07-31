"""API 请求模型定义。"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator

from server.services.naming import normalize_text


class TrimmedStringModel(BaseModel):
    """自动规范化字符串字段的基类模型。"""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def normalize_string_fields(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float)):
            return normalize_text(value)
        return value

    @field_validator("callback_url", check_fields=False)
    @classmethod
    def validate_callback_url(cls, value: str) -> str:
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("callback_url must be an HTTP URL")
        return value


class NationShareQuery(TrimmedStringModel):
    taskId: str


class NationRegionRequest(TrimmedStringModel):
    name: str
    adcode: str
    value: str

    @field_validator("adcode")
    @classmethod
    def validate_adcode(cls, value: str) -> str:
        if not value:
            raise ValueError("regions adcode is required")
        return value


class NationSnapshotCreateRequest(TrimmedStringModel):
    regions: list[NationRegionRequest]
    value_label: str
    callback_url: str = ""

    @field_validator("regions")
    @classmethod
    def validate_regions(
        cls, value: list[NationRegionRequest]
    ) -> list[NationRegionRequest]:
        if not value:
            raise ValueError("regions must not be empty")
        return value


class ProvinceShareQuery(TrimmedStringModel):
    taskId: str


class ProvinceRequest(TrimmedStringModel):
    name: str = ""
    adcode: str

    @field_validator("adcode")
    @classmethod
    def validate_adcode(cls, value: str) -> str:
        if not value:
            raise ValueError("province.adcode is required")
        return value


class ProvinceRegionRequest(TrimmedStringModel):
    name: str = ""
    adcode: str
    value: str = ""

    @field_validator("adcode")
    @classmethod
    def validate_adcode(cls, value: str) -> str:
        if not value:
            raise ValueError("regions adcode is required")
        return value


class ProvinceSnapshotCreateRequest(TrimmedStringModel):
    province: ProvinceRequest
    regions: list[ProvinceRegionRequest]
    value_label: str = "状态"
    callback_url: str = ""

    @field_validator("regions")
    @classmethod
    def validate_regions(
        cls, value: list[ProvinceRegionRequest]
    ) -> list[ProvinceRegionRequest]:
        if not value:
            raise ValueError("regions must not be empty")
        return value


class CityShareQuery(TrimmedStringModel):
    taskId: str


class CityRequest(TrimmedStringModel):
    name: str = ""
    adcode: str

    @field_validator("adcode")
    @classmethod
    def validate_adcode(cls, value: str) -> str:
        if not value:
            raise ValueError("city.adcode is required")
        if not value.endswith("00"):
            raise ValueError("city adcode must end with '00'")
        return value


class DistrictRequest(TrimmedStringModel):
    name: str = ""
    adcode: str
    value: str = ""

    @field_validator("adcode")
    @classmethod
    def validate_adcode(cls, value: str) -> str:
        if not value:
            raise ValueError("district adcode is required")
        if value.endswith("00"):
            raise ValueError("district adcode must not end with '00'")
        return value


class CitySnapshotCreateRequest(TrimmedStringModel):
    city: CityRequest
    districts: list[DistrictRequest]
    value_label: str = "状态"
    callback_url: str = ""

    @field_validator("districts")
    @classmethod
    def validate_districts(cls, value: list[DistrictRequest]) -> list[DistrictRequest]:
        if not value:
            raise ValueError("districts must not be empty")
        return value
