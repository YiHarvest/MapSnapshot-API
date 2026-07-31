"""系统路由、任务查询和截图资源接口。"""

# ruff: noqa: F403, F405

from __future__ import annotations

from server import *  # noqa: F403


def register_system_routes(
    app: FastAPI,
    router: APIRouter,
    state: RuntimeState,
) -> None:
    """注册所有截图类型共享的系统路由。"""

    @app.get("/dO3j6iTFfD.txt", include_in_schema=False)
    async def verification_file() -> FileResponse:
        return FileResponse(app.state.static_dir / "dO3j6iTFfD.txt")

    @router.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "region-view-snapshot-server"}

    @router.get("/snapshots/{file_name}")
    def get_snapshot(file_name: str) -> FileResponse:
        safe_name = SNAPSHOT_DIR.joinpath(file_name).name
        file_path = SNAPSHOT_DIR / safe_name
        if file_path.suffix.lower() != ".png" or not file_path.exists():
            raise HTTPException(status_code=404, detail="image not found")
        return FileResponse(
            path=str(file_path),
            media_type="image/png",
            filename=safe_name,
            headers={"Cache-Control": "public, max-age=31536000"},
        )

    @router.get("/snapshot/{task_id}")
    async def snapshot_query(task_id: str):
        task = state.tasks.get(task_id)
        if task is None:
            task = await load_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="task not found")
        status_code = 500 if task["status"] == "failed" else 200
        return JSONResponse(
            content={
                "success": task["status"] != "failed",
                "data": serialize_public_task(task),
            },
            status_code=status_code,
        )
