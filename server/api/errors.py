"""统一 HTTP 异常响应。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


def _validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for error in exc.errors():
        location = [str(part) for part in error["loc"] if part != "body"]
        message = str(error["msg"]).removeprefix("Value error, ")
        errors.append(
            {
                "field": ".".join(location),
                "message": message,
                "type": error["type"],
            }
        )
    return errors


def register_exception_handlers(app: FastAPI) -> None:
    """注册统一 JSON 错误响应。"""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": "request validation failed",
                "errors": _validation_errors(exc),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(
        _request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "message": str(exc.detail)},
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("Unhandled request error: %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "internal server error"},
        )
