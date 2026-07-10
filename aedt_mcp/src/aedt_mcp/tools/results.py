"""Results / post-processing tools (Maxwell + HFSS).

Pulls solution data via pyaedt's `SolutionData` API and writes CSV snapshots
to the `out/` dir for downstream NN training datasets.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import numpy as np

from ..pyansys_api import handle_errors, ok
from ..schemas import (
    GetFluxLinkageArgs,
    GetSolutionDataArgs,
    GetTorqueArgs,
    GetWindingInductanceArgs,
)
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.results")

OUT_DIR = os.path.abspath(os.environ.get("AEDT_MCP_OUT_DIR", "out"))


def _client(design_type: str):
    return SESSION.require_active(design_type)


def _out_path(basename: str, ext: str = "csv") -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(OUT_DIR, f"{basename}_{ts}.{ext}")


def _solution_data(args: GetSolutionDataArgs):
    """Internal: fetch SolutionData + write CSV + return summary dict."""
    c = _client(args.design_type)
    setup = args.setup or (c.nominal_adaptive_setup if hasattr(c, "nominal_adaptive_setup") else
                           (c.setup_names[0] if c.setup_names else None))

    sol = c.post.get_solution_data(
        expressions=args.expressions,
        setup_sweep_name=setup,
        primary_sweep_variable=args.primary_sweep,
        report_category=args.report_category,
        variations=args.variations,
    )
    out: dict[str, Any] = {
        "expressions": args.expressions,
        "primary_sweep": args.primary_sweep,
        "setup": setup,
        "design": c.design_name,
    }
    files: list[str] = []
    if sol is False or sol is None:
        out["error"] = "no solution data available"
        return out, files
    if args.write_csv:
        # SolutionData.export_data_to_csv writes the full sweep table.
        path = _out_path(args.csv_basename or f"{c.design_name}_{setup or 'setup'}", "csv")
        try:
            sol.export_data_to_csv(path)
            files.append(path)
            out["csv"] = path
        except Exception as exc:
            logger.warning("export_data_to_csv failed: %s", exc)
            try:
                c.post.export_report_to_csv(OUT_DIR, sol.expressions[0])
                files.append(OUT_DIR)
            except Exception:
                pass
    # Attach first expression arrays so the LLM gets the shape without re-reading file.
    try:
        sweeps, arr = sol.get_expression_data(args.expressions[0])
        out["primary_sweep_values"] = {
            "length": int(np.asarray(sweeps).size),
            "first": float(np.asarray(sweeps).flatten()[0]),
            "last": float(np.asarray(sweeps).flatten()[-1]),
        }
    except Exception as exc:
        out["primary_sweep_values"] = {"error": f"{exc}"}
    return out, files


@handle_errors
def get_solution_data(args: GetSolutionDataArgs) -> dict[str, Any]:
    """Fetch solution data for the given expressions and dump to CSV."""
    out, files = _solution_data(args)
    return ok(out, files=files).payload


@handle_errors
def get_torque(args: GetTorqueArgs) -> dict[str, Any]:
    """Fetch torque vs primary sweep (Time or Angle) from the active Maxwell design."""
    expr = [args.torque_name]
    nested = GetSolutionDataArgs(
        design_type="maxwell3d",
        expressions=expr,
        primary_sweep="Time",
        setup=args.setup,
        write_csv=args.write_csv,
        csv_basename=f"torque_{args.torque_name}",
    )
    base, files = _solution_data(nested)
    return ok(base, files=files).payload


@handle_errors
def get_flux_linkage(args: GetFluxLinkageArgs) -> dict[str, Any]:
    """Fetch flux linkage of a winding vs Time from the active Maxwell design."""
    expr = [f"FluxLinkage({args.winding})"]
    nested = GetSolutionDataArgs(
        design_type="maxwell3d",
        expressions=expr,
        primary_sweep="Time",
        setup=args.setup,
        write_csv=args.write_csv,
        csv_basename=f"fluxlink_{args.winding}",
    )
    base, files = _solution_data(nested)
    return ok(base, files=files).payload


@handle_errors
def get_winding_inductance(args: GetWindingInductanceArgs) -> dict[str, Any]:
    """Compute winding inductance matrix summary for a magnetostatic setup."""
    c = SESSION.require_active("maxwell3d")
    matrices = []
    try:
        if hasattr(c, "get_matrix") and args.winding in (c.windings or []):
            m = c.get_matrix(args.winding)
            matrices.append(getattr(m, "matrix", {}))
    except Exception as exc:
        logger.warning("get_matrix fallback: %s", exc)
    if not matrices:
        # Use available quantities as the simplest safe fallback.
        try:
            qs = c.post.available_report_quantities(report_category="Matrix")
            matrices.append({"quantities_available": list(qs)})
        except Exception as exc:
            matrices.append({"error": f"{exc}"})
    return {"setup": args.setup, "winding": args.winding, "matrices": matrices}