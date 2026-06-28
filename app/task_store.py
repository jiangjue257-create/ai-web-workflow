from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def create(self, *, kind: str, prompt: str) -> dict[str, Any]:
        now = _now_iso()
        task = {
            "id": uuid4().hex,
            "kind": kind,
            "prompt": prompt,
            "status": "pending",
            "message": "等待开始",
            "error": "",
            "file_url": "",
            "file_name": "",
            "raw": None,
            "created_at": now,
            "updated_at": now,
        }

        with self._lock:
            self._tasks[task["id"]] = task
            return deepcopy(task)

    def update(self, task_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            task = self._tasks[task_id]
            task.update(fields)
            task["updated_at"] = _now_iso()
            return deepcopy(task)

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return deepcopy(task)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
