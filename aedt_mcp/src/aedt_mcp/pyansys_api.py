"""Thin wrappers around PyAnsys calls + structured error / result types."""

from __future__ import annotations

import json
import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

logger = logging.getLogger("aedt_mcp")


@dataclass
class ToolError(Exception):
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


@dataclass
class ToolResult:
    """Structured result returned from a tool handler.

    `payload` is JSON-serializable. `files` is a list of absolute file paths
    produced by the tool (datasets, field exports, etc.).
    """

    payload: Any
    files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def to_json(obj: Any) -> str:
    try:
        return json.dumps(obj, default=str, indent=2)
    except (TypeError, ValueError):
        return json.dumps({"str": str(obj)})


def handle_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate a tool handler so any pyaedt/Python exception becomes a
    ToolError with traceback, instead of killing the stdio loop."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface to LLM as text
            logger.exception("Tool %s failed", fn.__name__)
            raise ToolError(
                message=f"{type(exc).__name__}: {exc}",
                details={"traceback": traceback.format_exc(limit=4)},
            ) from exc

    return wrapper


def ok(payload: Any, files: list[str] | None = None, notes: list[str] | None = None) -> ToolResult:
    return ToolResult(payload=payload, files=files or [], notes=notes or [])