from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Condition, Lock
from time import monotonic


class MaintenanceBusyError(RuntimeError):
    pass


class MaintenanceGate:
    def __init__(self) -> None:
        self._condition = Condition(Lock())
        self._operation_lock = Lock()
        self._maintenance_active = False
        self._active_writes = 0
        self._operation: str | None = None

    @property
    def active(self) -> bool:
        with self._condition:
            return self._maintenance_active

    @property
    def operation(self) -> str | None:
        with self._condition:
            return self._operation

    def begin_write(self) -> bool:
        with self._condition:
            if self._maintenance_active:
                return False
            self._active_writes += 1
            return True

    def end_write(self) -> None:
        with self._condition:
            self._active_writes = max(0, self._active_writes - 1)
            self._condition.notify_all()

    @contextmanager
    def maintenance(self, operation: str, *, wait_seconds: float = 15.0) -> Iterator[None]:
        if not self._operation_lock.acquire(blocking=False):
            raise MaintenanceBusyError("另一个数据库维护操作正在执行。")
        try:
            with self._condition:
                self._maintenance_active = True
                self._operation = operation
                deadline = monotonic() + wait_seconds
                while self._active_writes:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise MaintenanceBusyError("仍有写请求未结束，无法进入维护状态。")
                    self._condition.wait(timeout=remaining)
            yield
        finally:
            with self._condition:
                self._maintenance_active = False
                self._operation = None
                self._condition.notify_all()
            self._operation_lock.release()


maintenance_gate = MaintenanceGate()
