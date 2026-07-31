import importlib.util


def test_legacy_server_config_module_is_removed() -> None:
    assert importlib.util.find_spec("server.config") is None


def test_server_package_exposes_shared_application_dependencies() -> None:
    from server import (
        BASE_URL,
        DEFAULT_PORT,
        DEVICE_SCALE_FACTOR,
        SCREENSHOT_DELAY_MS,
        VIEWPORT,
        APIRouter,
        CityShareQuery,
        CitySnapshotCreateRequest,
        CORSMiddleware,
        Depends,
        FastAPI,
        FastAPIRequest,
        FileResponse,
        HTMLResponse,
        HTTPException,
        NationShareQuery,
        NationSnapshotCreateRequest,
        Path,
        ProvinceShareQuery,
        ProvinceSnapshotCreateRequest,
        StaticFiles,
        TrimmedStringModel,
        build_callback_payload,
        build_region_index,
        cleanup_expired_tasks,
        register_city_snapshot_routes,
        register_national_snapshot_routes,
        register_province_snapshot_routes,
        register_system_routes,
        shutdown_runtime_resources,
    )

    assert all(
        dependency is not None
        for dependency in (
            APIRouter,
            BASE_URL,
            CityShareQuery,
            CitySnapshotCreateRequest,
            CORSMiddleware,
            Depends,
            DEVICE_SCALE_FACTOR,
            DEFAULT_PORT,
            FastAPI,
            FastAPIRequest,
            FileResponse,
            HTMLResponse,
            HTTPException,
            NationShareQuery,
            NationSnapshotCreateRequest,
            Path,
            ProvinceShareQuery,
            ProvinceSnapshotCreateRequest,
            SCREENSHOT_DELAY_MS,
            StaticFiles,
            TrimmedStringModel,
            VIEWPORT,
            build_callback_payload,
            build_region_index,
            cleanup_expired_tasks,
            register_city_snapshot_routes,
            register_national_snapshot_routes,
            register_province_snapshot_routes,
            register_system_routes,
            shutdown_runtime_resources,
        )
    )


def test_core_package_exposes_core_dependencies() -> None:
    from server.core import (
        DEFAULT_PORT,
        PUBLIC_DIR,
        RuntimeState,
        SnapshotContext,
        build_lifespan,
        shutdown_runtime_resources,
    )

    assert all(
        dependency is not None
        for dependency in (
            DEFAULT_PORT,
            PUBLIC_DIR,
            SnapshotContext,
            RuntimeState,
            build_lifespan,
            shutdown_runtime_resources,
        )
    )


def test_services_package_exposes_service_dependencies() -> None:
    from server.services import (
        RegionService,
        build_callback_payload,
        build_region_index,
        capture_share_page,
        cleanup_expired_tasks,
        render_share_template,
        send_callback,
    )

    assert all(
        dependency is not None
        for dependency in (
            RegionService,
            build_callback_payload,
            build_region_index,
            capture_share_page,
            cleanup_expired_tasks,
            render_share_template,
            send_callback,
        )
    )


def test_api_package_exposes_route_registrars() -> None:
    from server.api import (
        register_city_snapshot_routes,
        register_national_snapshot_routes,
        register_province_snapshot_routes,
        register_system_routes,
    )

    assert all(
        registrar is not None
        for registrar in (
            register_city_snapshot_routes,
            register_national_snapshot_routes,
            register_province_snapshot_routes,
            register_system_routes,
        )
    )
