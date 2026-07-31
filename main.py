"""命令行入口。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn

from server import DEFAULT_PORT, PUBLIC_DIR


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse server command-line arguments."""

    parser = argparse.ArgumentParser(description="Run the map snapshot API")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="restart the server when Python or GeoJSON files change",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Run Uvicorn with the requested development options."""

    args = parse_args(argv)
    options: dict[str, object] = {
        "host": "0.0.0.0",
        "port": DEFAULT_PORT,
        "reload": args.reload,
    }
    if args.reload:
        options["reload_dirs"] = ["server", str(PUBLIC_DIR / "geojson")]
    uvicorn.run("server.app:app", **options)


if __name__ == "__main__":
    main()
