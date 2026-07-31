import asyncio
from typing import Any

import httpx

from server.app import create_app

EXPECTED_PATHS = {
    "/dO3j6iTFfD.txt",
    "/api/v1/health",
    "/api/v1/map-share",
    "/api/v1/province-share",
    "/api/v1/city-share",
    "/api/v1/snapshot",
    "/api/v1/province-snapshot",
    "/api/v1/city-snapshot",
    "/api/v1/snapshot/{task_id}",
    "/api/v1/snapshots/{file_name}",
}


def request(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, json=json)

    return asyncio.run(send())


def test_create_app_registers_compatible_public_routes() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}

    assert EXPECTED_PATHS <= paths


def test_health_contract_is_unchanged() -> None:
    response = request("GET", "/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "region-view-snapshot-server",
    }


def test_unknown_task_uses_existing_error_envelope() -> None:
    response = request("GET", "/api/v1/snapshot/missing-task")

    assert response.status_code == 404
    assert response.json() == {"success": False, "message": "task not found"}


def test_invalid_city_request_uses_validation_error_envelope() -> None:
    response = request(
        "POST",
        "/api/v1/city-snapshot",
        json={"city": {"adcode": "330100"}, "districts": []},
    )

    assert response.status_code == 422
    assert response.json() == {
        "success": False,
        "message": "request validation failed",
        "errors": [
            {
                "field": "districts",
                "message": "districts must not be empty",
                "type": "value_error",
            }
        ],
    }


def test_http_error_uses_shared_error_envelope() -> None:
    response = request("GET", "/api/v1/snapshots/missing.png")

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "message": "image not found",
    }


def test_unexpected_error_uses_shared_error_envelope() -> None:
    app = create_app()

    @app.get("/test-error")
    async def test_error() -> None:
        raise RuntimeError("private failure detail")

    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/test-error")

    response = asyncio.run(send())

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "message": "internal server error",
    }
