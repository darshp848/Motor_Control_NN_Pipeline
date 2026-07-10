"""Solve / analyze tools."""

from __future__ import annotations

import logging
import time
from typing import Any

from ..pyansys_api import handle_errors
from ..schemas import AnalyzeSetupArgs, GetSolveStatusArgs
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.solve")


def _client(design_type: str):
    return SESSION.require_active(design_type)


@handle_errors
def analyze_setup(args: AnalyzeSetupArgs) -> dict[str, Any]:
    """Run analysis on a setup (or all setups if name='all'). Blocks by default."""
    c = _client(args.design_type)
    t0 = time.time()
    if args.name == "all":
        c.analyze_all()
        setups = list(c.setup_names)
    else:
        c.analyze_setup(args.name, blocking=args.block)
        setups = [args.name]
    elapsed = time.time() - t0
    return {"analyzed": setups, "blocked": args.block, "elapsed_s": round(elapsed, 2)}


@handle_errors
def get_solve_status(args: GetSolveStatusArgs) -> dict[str, Any]:
    c = _client(args.design_type)
    try:
        names = c.setup_names
    except Exception:
        names = []
    if args.name not in names:
        return {"setup": args.name, "found": False, "setups": list(names)}
    try:
        setup = c.get_setup(args.name)
        status = "solved" if (setup and hasattr(setup, "is_solved") and setup.is_solved) else "unknown"
    except Exception as exc:
        status = f"error: {exc}"
    return {"setup": args.name, "found": True, "status": status}