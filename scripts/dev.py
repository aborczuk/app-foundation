"""Start the local financial tracker database, API, and browser development server."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.financial-tracker.yml"
DEFAULT_DATABASE_URL = "postgresql://financial_tracker:financial_tracker_dev@localhost:55432/financial_tracker"


def wait_for_url(url: str, *, timeout_seconds: float = 30.0) -> None:
    """Wait until a local HTTP endpoint responds or raise a startup error."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except (OSError, URLError) as exc:
            last_error = exc
        time.sleep(0.25)
    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(f"Timed out waiting for {url}{detail}")


def start_database() -> None:
    """Start the disposable PostgreSQL service and wait for its healthcheck."""
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "--wait"],
        cwd=PROJECT_ROOT,
        check=True,
    )


def start_processes(database_url: str) -> list[subprocess.Popen[bytes]]:
    """Start API and browser processes with inherited terminal output."""
    environment = os.environ.copy()
    environment["FINANCIAL_TRACKER_TEST_DATABASE_URL"] = database_url
    processes: list[subprocess.Popen[bytes]] = []
    try:
        processes.append(
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "financial_tracker.app:app", "--host", "127.0.0.1", "--port", "8000"],
                cwd=PROJECT_ROOT,
                env=environment,
            )
        )
        processes.append(
            subprocess.Popen(
                ["npm", "run", "dev", "--", "--host", "127.0.0.1"],
                cwd=FRONTEND_ROOT,
                env=environment,
            )
        )
        return processes
    except BaseException:
        stop_processes(processes)
        raise


def stop_processes(processes: list[subprocess.Popen[bytes]]) -> None:
    """Terminate child processes and force-close any that do not exit promptly."""
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    for process in reversed(processes):
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def parse_args() -> argparse.Namespace:
    """Parse the one optional local database override."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("FINANCIAL_TRACKER_TEST_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="PostgreSQL URL passed to the API process.",
    )
    return parser.parse_args()


def main() -> int:
    """Start the local stack and keep it alive until interrupted."""
    args = parse_args()
    processes: list[subprocess.Popen[bytes]] = []
    try:
        start_database()
        processes = start_processes(args.database_url)
        wait_for_url("http://127.0.0.1:8000/health")
        wait_for_url("http://127.0.0.1:5173/")
        print("Financial Tracker is ready at http://localhost:5173", flush=True)
        print("Press Ctrl-C to stop the API and frontend processes.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(1)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
