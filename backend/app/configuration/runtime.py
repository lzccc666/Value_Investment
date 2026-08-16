from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import TypeVar

from app.configuration.defaults import default_parameter_config

T = TypeVar("T")

_active_parameter_config: ContextVar[dict[str, object] | None] = ContextVar(
    "active_parameter_config",
    default=None,
)


@contextmanager
def parameter_config_context(config: dict[str, object]) -> Iterator[None]:
    token = _active_parameter_config.set(deepcopy(config))
    try:
        yield
    finally:
        _active_parameter_config.reset(token)


def active_parameter_config() -> dict[str, object]:
    current = _active_parameter_config.get()
    return current if current is not None else default_parameter_config()


def parameter_value(path: str, default: T) -> T:
    value: object = active_parameter_config()
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value  # type: ignore[return-value]
