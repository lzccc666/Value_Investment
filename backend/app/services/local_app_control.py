import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


def get_stop_request_file() -> Path | None:
    if not settings.local_app_control_enabled:
        return None
    if not settings.local_control_token or len(settings.local_control_token) < 32:
        return None
    if settings.stop_request_file is None:
        return None

    runtime_directory = settings.runtime_directory.resolve()
    stop_request_file = settings.stop_request_file.resolve()
    if stop_request_file.parent != runtime_directory:
        return None
    if not stop_request_file.name.startswith("stop-") or stop_request_file.suffix != ".request":
        return None
    return stop_request_file


def is_local_app_control_ready() -> bool:
    return get_stop_request_file() is not None


def create_local_shutdown_request() -> None:
    stop_request_file = get_stop_request_file()
    if stop_request_file is None:
        raise RuntimeError("Local app control is not available.")

    stop_request_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = stop_request_file.with_name(
        f".{stop_request_file.name}.{uuid4().hex}.tmp"
    )
    payload = {
        "status": "requested",
        "requested_at_utc": datetime.now(UTC).isoformat(),
    }
    temporary_file.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary_file, stop_request_file)
