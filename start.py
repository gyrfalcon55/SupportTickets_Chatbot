"""Launch FastAPI and Streamlit together from one command."""

import os
import subprocess
import sys
import time
from pathlib import Path
from app.db.initialize_db import build_database
import logging
import sqlite3

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = os.getenv("API_PORT", "8000")
STREAMLIT_PORT = os.getenv("STREAMLIT_PORT", "8501")

API_MODULE = os.getenv("API_MODULE", "app.api.main:app")
STREAMLIT_FILE = os.getenv(
    "STREAMLIT_FILE",
    "app/ui/streamlit_app.py",
)


def main():
    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        API_MODULE,
        "--host",
        API_HOST,
        "--port",
        API_PORT,
    ]

    streamlit_path = ROOT / STREAMLIT_FILE

    streamlit_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(streamlit_path),
        "--server.port",
        STREAMLIT_PORT,
        "--server.address",
        "127.0.0.1",
    ]

    processes = []

    try:
        print(f"Starting FastAPI at http://{API_HOST}:{API_PORT}")
        api = subprocess.Popen(api_cmd, cwd=ROOT)
        processes.append(api)

        time.sleep(1)

        if api.poll() is not None:
            raise RuntimeError(
                f"FastAPI exited early with code {api.returncode}"
            )

        if not streamlit_path.exists():
            raise FileNotFoundError(
                f"Streamlit file not found: {streamlit_path}"
            )

        print(
            f"Starting Streamlit at "
            f"http://127.0.0.1:{STREAMLIT_PORT}"
        )
        streamlit = subprocess.Popen(streamlit_cmd, cwd=ROOT)
        processes.append(streamlit)

        print("\nBoth services are running. Press Ctrl+C to stop.\n")
        try:
            res = build_database()
            print(f"res\n")
        except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
            raise SystemExit(f"Database initialization failed: {exc}") from exc

        while all(proc.poll() is None for proc in processes):
            time.sleep(0.5)

        failed = [
            proc.returncode
            for proc in processes
            if proc.returncode not in (None, 0)
        ]

        if failed:
            raise SystemExit(
                f"A service exited with non-zero status: {failed}"
            )

    except KeyboardInterrupt:
        print("\nStopping services...")

    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()

        for proc in processes:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        print("Services stopped.")


if __name__ == "__main__":
    main()