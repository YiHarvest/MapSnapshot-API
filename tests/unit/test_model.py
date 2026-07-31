from pydantic import BaseModel

from server.model import (
    CitySnapshotCreateRequest,
    NationSnapshotCreateRequest,
    ProvinceSnapshotCreateRequest,
    TrimmedStringModel,
)


def test_model_module_exposes_shared_base_model() -> None:
    assert issubclass(TrimmedStringModel, BaseModel)


def test_model_module_exposes_all_snapshot_requests() -> None:
    assert NationSnapshotCreateRequest.__name__ == "NationSnapshotCreateRequest"
    assert ProvinceSnapshotCreateRequest.__name__ == "ProvinceSnapshotCreateRequest"
    assert CitySnapshotCreateRequest.__name__ == "CitySnapshotCreateRequest"
