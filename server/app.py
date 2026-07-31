"""FastAPI 应用入口。"""

# ruff: noqa: F403, F405

from __future__ import annotations

from server import *  # noqa: F403


def create_app(state: RuntimeState | None = None) -> FastAPI:
    """创建独立的 FastAPI 应用实例及其运行时依赖。"""

    runtime = state or RuntimeState()
    regions = RegionService(runtime)
    app = FastAPI(
        title="Region View Snapshot Server",
        lifespan=build_lifespan(runtime),
    )
    register_exception_handlers(app)
    app.state.runtime = runtime

    static_dir = Path(__file__).resolve().parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.state.static_dir = static_dir
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.mount(
        "/geojson",
        StaticFiles(directory=PUBLIC_DIR / "geojson"),
        name="geojson",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    router = APIRouter(prefix="/api/v1")
    register_system_routes(app, router, runtime)
    context = SnapshotContext(
        task_store=runtime.tasks,
        browser_pool=runtime.browser_pool,
        get_screenshot_semaphore=runtime.get_screenshot_semaphore,
        generate_task_id=generate_task_id,
        get_origin=get_origin,
        send_callback=send_callback,
        infer_level=infer_level,
        get_region_index=regions.get_index,
        resolve_regions=regions.resolve_regions,
    )
    register_national_snapshot_routes(router, context)
    register_province_snapshot_routes(router, context)
    register_city_snapshot_routes(router, context)
    app.include_router(router)
    return app


app = create_app()
