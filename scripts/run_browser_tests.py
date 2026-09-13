"""Run real-browser tests with a disposable DB and isolated API/Vite ports.

Uses the existing local EVM contract; never modifies application households.
All subprocesses and the temporary database are cleaned up, even on failure.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402


def run() -> int:
    settings = get_settings()
    name = "urjasetu_browser_" + uuid4().hex[:12]
    maintenance = make_url(settings.maintenance_database_url or settings.database_url).set(
        database="postgres"
    )
    admin = create_engine(maintenance, isolation_level="AUTOCOMMIT")
    test_url = (
        make_url(settings.database_url).set(database=name).render_as_string(hide_password=False)
    )
    env = dict(
        os.environ,
        DATABASE_URL=test_url,
        APP_ENV="development",
        SIMULATION_WORKER_ENABLED="true",
        ALLOW_LEGACY_TEST_API="false",
        CORS_ALLOWED_ORIGINS='["http://127.0.0.1:5174"]',
        BACKEND_TARGET="http://127.0.0.1:8001",
        PLAYWRIGHT_BASE_URL="http://127.0.0.1:5174",
        GEMINI_API_KEY="",
    )
    python = str(ROOT / ".venv/bin/python")
    logs = ROOT / ".runtime"
    logs.mkdir(exist_ok=True)
    processes: list[subprocess.Popen] = []
    handles = []
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    print(f"Browser test database: {name} (temporary)", flush=True)
    try:
        subprocess.run(
            [python, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend", env=env, check=True
        )
        subprocess.run(
            [python, "scripts/bootstrap_workspace.py"],
            cwd=ROOT,
            env=dict(env, PYTHONPATH="backend"),
            check=True,
        )
        for label, command, cwd in (
            (
                "browser-api",
                [
                    python,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--app-dir",
                    "backend",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8001",
                ],
                ROOT,
            ),
            (
                "browser-vite",
                [
                    "node",
                    "node_modules/vite/bin/vite.js",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5174",
                    "--strictPort",
                ],
                ROOT / "frontend",
            ),
        ):
            handle = (logs / f"{label}.log").open("w")
            handles.append(handle)
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            )
        for _ in range(40):
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(
                    "An isolated server could not start; inspect .runtime/browser-*.log."
                )
            try:
                if (
                    httpx.get("http://127.0.0.1:8001/health/ready", timeout=1).is_success
                    and httpx.get("http://127.0.0.1:5174", timeout=1).is_success
                ):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Timed out starting isolated browser services.")
        return subprocess.run(
            ["npm", "run", "test:e2e", "--", *sys.argv[1:]], cwd=ROOT / "frontend", env=env
        ).returncode
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for handle in handles:
            handle.close()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
        print("Isolated browser services stopped; temporary database removed.", flush=True)


if __name__ == "__main__":
    raise SystemExit(run())
