import asyncio
from types import SimpleNamespace

from server.services.execution import (
    execute_snapshot_task,
    run_background_task,
    schedule_background_task,
    schedule_snapshot_task,
    send_callback_safely,
)


def test_send_callback_safely_records_callback_error() -> None:
    task: dict[str, object] = {}

    async def failing_callback(
        _task: dict[str, object],
        _origin: str,
    ) -> None:
        raise RuntimeError("callback unavailable")

    asyncio.run(
        send_callback_safely(
            task=task,
            origin="http://example.test",
            callback=failing_callback,
        )
    )

    assert task["callbackError"] == "callback unavailable"


def test_run_background_task_persists_a_guarded_failure() -> None:
    task = {"taskId": "failed-task", "status": "processing"}
    persisted: list[dict[str, object]] = []

    async def failing_runner(
        _task_id: str,
        _origin: str,
        _context: object,
    ) -> None:
        raise RuntimeError("render failed")

    async def persist(value: dict[str, object]) -> None:
        persisted.append(dict(value))

    context = SimpleNamespace(
        task_store={"failed-task": task},
        get_screenshot_semaphore=lambda: asyncio.Semaphore(1),
    )

    asyncio.run(
        run_background_task(
            task_id="failed-task",
            origin="http://example.test",
            context=context,
            runner=failing_runner,
            persist=persist,
        )
    )

    assert task["status"] == "failed"
    assert task["message"] == "render failed"
    assert persisted == [
        {"taskId": "failed-task", "status": "failed", "message": "render failed"}
    ]


def test_run_background_task_guards_failure_without_semaphore() -> None:
    task = {"taskId": "failed-task", "status": "processing"}
    persisted: list[dict[str, object]] = []

    async def failing_runner(
        _task_id: str,
        _origin: str,
        _context: object,
    ) -> None:
        raise RuntimeError("render failed")

    async def persist(value: dict[str, object]) -> None:
        persisted.append(dict(value))

    context = SimpleNamespace(
        task_store={"failed-task": task},
        get_screenshot_semaphore=lambda: None,
    )

    asyncio.run(
        run_background_task(
            task_id="failed-task",
            origin="http://example.test",
            context=context,
            runner=failing_runner,
            persist=persist,
        )
    )

    assert task["status"] == "failed"
    assert task["message"] == "render failed"
    assert persisted == [
        {"taskId": "failed-task", "status": "failed", "message": "render failed"}
    ]


def test_execute_snapshot_task_owns_capture_persistence_and_callback(tmp_path) -> None:
    task = {
        "taskId": "snapshot-task",
        "status": "processing",
        "mapUrl": "http://example.test/share",
    }
    persisted: list[dict[str, object]] = []
    callbacks: list[tuple[dict[str, object], str]] = []
    captures: list[tuple[object, str, object]] = []

    async def prepare(
        _task: dict[str, object],
        _context: object,
    ) -> bool:
        return True

    async def capture(*, browser: object, url: str, output_path: object) -> None:
        captures.append((browser, url, output_path))

    async def callback(
        value: dict[str, object],
        origin: str,
    ) -> None:
        callbacks.append((value, origin))

    async def persist(value: dict[str, object]) -> None:
        persisted.append(dict(value))

    browser = object()
    context = SimpleNamespace(
        task_store={"snapshot-task": task},
        browser_pool={"browser": browser},
        send_callback=callback,
    )

    asyncio.run(
        execute_snapshot_task(
            task_id="snapshot-task",
            origin="http://example.test",
            context=context,
            prepare=prepare,
            map_key="test-key",
            capture=capture,
            persist=persist,
            snapshot_dir=tmp_path,
        )
    )

    assert task["status"] == "done"
    assert task["imageUrl"] == (
        "http://example.test/api/v1/snapshots/snapshot-task.png"
    )
    assert captures == [
        (
            browser,
            "http://example.test/share",
            tmp_path / "snapshot-task.png",
        )
    ]
    assert persisted == [task]
    assert callbacks == [(task, "http://example.test")]


def test_execute_snapshot_task_stops_when_map_key_is_missing(tmp_path) -> None:
    task = {"taskId": "snapshot-task", "status": "processing"}
    persisted: list[dict[str, object]] = []
    prepare_called = False

    async def prepare(
        _task: dict[str, object],
        _context: object,
    ) -> bool:
        nonlocal prepare_called
        prepare_called = True
        return True

    async def callback(
        _task: dict[str, object],
        _origin: str,
    ) -> None:
        return None

    async def persist(value: dict[str, object]) -> None:
        persisted.append(dict(value))

    context = SimpleNamespace(
        task_store={"snapshot-task": task},
        browser_pool={"browser": object()},
        send_callback=callback,
    )

    asyncio.run(
        execute_snapshot_task(
            task_id="snapshot-task",
            origin="http://example.test",
            context=context,
            prepare=prepare,
            map_key="",
            persist=persist,
            snapshot_dir=tmp_path,
        )
    )

    assert prepare_called is False
    assert task["status"] == "failed"
    assert task["message"] == "missing VITE_AMAP_KEY"
    assert persisted == [task]


def test_schedule_background_task_runs_shared_runner() -> None:
    calls: list[tuple[str, str, object]] = []
    context = SimpleNamespace(
        task_store={},
        get_screenshot_semaphore=lambda: None,
    )

    async def runner(task_id: str, origin: str, value: object) -> None:
        calls.append((task_id, origin, value))

    async def run() -> None:
        scheduled = schedule_background_task(
            task_id="task-id",
            origin="http://example.test",
            context=context,
            runner=runner,
        )
        await scheduled

    asyncio.run(run())

    assert calls == [("task-id", "http://example.test", context)]


def test_schedule_snapshot_task_connects_prepare_to_shared_executor() -> None:
    calls: list[tuple[str, str, object, object]] = []
    context = SimpleNamespace(
        task_store={},
        get_screenshot_semaphore=lambda: None,
    )

    async def prepare(_task: dict[str, object], _context: object) -> bool:
        return True

    async def execute(
        *,
        task_id: str,
        origin: str,
        context: object,
        prepare: object,
    ) -> None:
        calls.append((task_id, origin, context, prepare))

    async def run() -> None:
        scheduled = schedule_snapshot_task(
            task_id="task-id",
            origin="http://example.test",
            context=context,
            prepare=prepare,
            execute=execute,
        )
        await scheduled

    asyncio.run(run())

    assert calls == [
        ("task-id", "http://example.test", context, prepare),
    ]
