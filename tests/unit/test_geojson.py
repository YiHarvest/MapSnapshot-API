import asyncio
import json

from server.services import geojson


def test_build_region_index_reads_geojson_asynchronously(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(geojson, "PUBLIC_DIR", tmp_path)
    geojson_dir = tmp_path / "geojson"
    geojson_dir.mkdir()
    (geojson_dir / "china.json").write_text(
        json.dumps(
            {
                "features": [
                    {
                        "properties": {
                            "adcode": "330000",
                            "center": [120.2, 30.3],
                            "level": "province",
                            "name": "浙江省",
                        }
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    index = asyncio.run(geojson.build_region_index())

    assert index["byAdcode"]["330000"] == {
        "name": "浙江省",
        "adcode": "330000",
        "level": "province",
        "center": [120.2, 30.3],
    }
