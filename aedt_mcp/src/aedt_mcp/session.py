"""PyAEDT session singleton.

Lazily launches a long-lived AEDT Desktop (non-graphical) on the first tool
call and keeps it alive for the MCP server's lifetime. Caches active Hfss /
Maxwell3d design clients keyed by ``<project>::<design>``.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from . import execution_policy as policy

logger = logging.getLogger("aedt_mcp")

DEFAULT_AEDT_VERSION = os.environ.get("AEDT_MCP_VERSION", "2025.2")
DEFAULT_STUDENT = os.environ.get("AEDT_MCP_STUDENT", "1") == "1"
DEFAULT_NON_GRAPHICAL = os.environ.get("AEDT_MCP_GRAPHICAL", "0") == "0"

try:
    from ansys.aedt.core import Desktop, Hfss, Maxwell3d  # type: ignore
    from ansys.aedt.core.generic.settings import settings as _aedt_settings  # type: ignore
    _PyaedtImportError: Exception | None = None
except Exception as _exc:  # pragma: no cover - exercised only when AEDT not yet installed
    Desktop = Hfss = Maxwell3d = None  # type: ignore[assignment]
    _aedt_settings = None
    _PyaedtImportError = _exc


DesignType = str  # "hfss" | "maxwell3d"


class AedtSessionError(RuntimeError):
    pass


class _AedtSession:
    """Module-level singleton holding the live Desktop + design registry."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._desktop: Any = None
        self._designs: dict[tuple[str, str, DesignType], Any] = {}
        self._active_key: tuple[str, str, DesignType] | None = None
        self._launch_params: dict[str, Any] | None = None

    # ----------------------------------------------------------------- launch
    def launch(
        self,
        version: str = DEFAULT_AEDT_VERSION,
        student_version: bool = DEFAULT_STUDENT,
        non_graphical: bool = DEFAULT_NON_GRAPHICAL,
    ) -> Any:
        with self._lock:
            if self._desktop is not None:
                return self._desktop
            decision = policy.decide_tool("open_design")
            if not decision.allowed:
                raise AedtSessionError(
                    "AEDT launch is blocked by execution policy. "
                    "Use aedt.generate_launch_procedure and aedt.generate_attach_test."
                )
            if _PyaedtImportError is not None:
                raise AedtSessionError(
                    "PyAnsys is not importable - run `pip install -e .` first. "
                    f"Underlying error: {_PyaedtImportError}"
                ) from _PyaedtImportError

            # Hint pyaedt at the Student install if env var present.
            ansysem_root = os.environ.get("ANSYSEM_ROOT")
            if ansysem_root:
                try:
                    _aedt_settings.aedt_install_dir = ansysem_root  # type: ignore[attr-defined]
                except Exception:
                    logger.warning("Could not set aedt_install_dir=%s", ansysem_root)

            logger.info("Launching AEDT %s student=%s non_graphical=%s", version, student_version, non_graphical)
            self._desktop = Desktop(
                version=version,
                non_graphical=non_graphical,
                new_desktop_session=True,
                student_version=student_version,
                close_on_exit=False,
            )
            self._launch_params = {
                "version": version,
                "student_version": student_version,
                "non_graphical": non_graphical,
            }
            return self._desktop

    @property
    def desktop(self) -> Any:
        if self._desktop is None:
            self.launch()
        return self._desktop

    @property
    def launch_params(self) -> dict[str, Any]:
        if self._launch_params is None:
            self.launch()
        return dict(self._launch_params or {})

    # ----------------------------------------------------- design registry
    def get_or_create(
        self,
        design_type: DesignType,
        project: str | None = None,
        design: str | None = None,
    ) -> Any:
        """Return a live Hfss/Maxwell3d client, creating it if needed."""
        if design_type not in ("hfss", "maxwell3d"):
            raise AedtSessionError(f"Unsupported design_type={design_type!r}")

        _ = self.desktop  # ensure launched (any import-time errors raised here)
        assert Desktop is not None and Hfss is not None and Maxwell3d is not None

        # Resolve project/design names after construction (pyaedt fills these in
        # with the active or a fresh project when None).
        cls = Hfss if design_type == "hfss" else Maxwell3d
        kwargs: dict[str, Any] = {}
        if project is not None:
            kwargs["project"] = project
        if design is not None:
            kwargs["design"] = design

        client = cls(new_desktop_session=False, **kwargs)
        key = (client.project_name, client.design_name, design_type)
        self._designs[key] = client
        self._active_key = key
        return client

    def list_designs(self) -> list[dict[str, str]]:
        return [
            {"project": p, "design": d, "type": t}
            for (p, d, t) in self._designs.keys()
        ]

    def active_for(self, design_type: DesignType) -> Any:
        """Return the most recently activated design of the given type, if any."""
        if self._active_key and self._active_key[2] == design_type:
            return self._designs.get(self._active_key)
        # fall back to any cached design of that type
        for key, client in self._designs.items():
            if key[2] == design_type:
                self._active_key = key
                return client
        return None

    def require_active(self, design_type: DesignType) -> Any:
        client = self.active_for(design_type)
        if client is None:
            raise AedtSessionError(
                f"No active {design_type} design. Call `open_design` "
                f"with design_type={design_type!r} first."
            )
        return client

    def set_active(self, project: str, design: str, design_type: DesignType) -> Any:
        key = (project, design, design_type)
        client = self._designs.get(key)
        if client is None:
            raise AedtSessionError(f"Design {key} is not registered.")
        self._active_key = key
        return client

    # ---------------------------------------------------------- shutdown
    def release(self) -> None:
        with self._lock:
            if self._desktop is not None:
                try:
                    self._desktop.release_desktop(False, False)
                except Exception:
                    pass
                self._desktop = None
            self._designs.clear()
            self._active_key = None


SESSION = _AedtSession()


def shutdown() -> None:
    SESSION.release()
