"""Parametric sweep tools (Maxwell + HFSS)."""

from __future__ import annotations

import logging
from typing import Any

from ..pyansys_api import ToolError, handle_errors, ok
from ..schemas import (
    AddVariationArgs,
    AnalyzeParametricArgs,
    CreateParametricSetupArgs,
    GetVariationTableArgs,
)
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.parametric")


def _client(design_type: str):
    return SESSION.require_active(design_type)


@handle_errors
def create_parametric_setup(args: CreateParametricSetupArgs) -> dict[str, Any]:
    """Create a parametric (Optimetrics) setup over design variables."""
    c = _client(args.design_type)
    variations: dict[str, Any] = {}
    for var in args.variables:
        variations[var] = {
            "point_count": args.point_count,
            "sweep_type": args.sweep_type,
        }
    param = c.parametrics.add(variations, name=args.name,
                               solution=args.setup_name,
                               save_fields=args.save_fields)
    return {"parametric_name": getattr(param, "name", args.name),
            "variables": list(variations.keys()), "setup": args.setup_name}


@handle_errors
def add_variation(args: AddVariationArgs) -> dict[str, Any]:
    c = _client(args.design_type)
    found = None
    for p in c.parametrics.setups:
        if getattr(p, "name", None) == args.parametric_name:
            found = p
            break
    if found is None:
        raise ToolError(f"Parametric setup {args.parametric_name!r} not found")
    found.add_variation(args.variable, start=args.start, stop=args.stop,
                        count=args.count, sweep_type=args.sweep_type)
    return {"parametric": args.parametric_name, "variable": args.variable,
            "range": [args.start, args.stop], "count": args.count}


@handle_errors
def analyze_parametric(args: AnalyzeParametricArgs) -> dict[str, Any]:
    c = _client(args.design_type)
    c.parametrics.analyze(args.parametric_name)
    return {"parametric": args.parametric_name, "analyzed": True}


@handle_errors
def get_variation_table(args: GetVariationTableArgs) -> dict[str, Any]:
    c = _client(args.design_type)
    found = None
    for p in c.parametrics.setups:
        if getattr(p, "name", None) == args.parametric_name:
            found = p
            break
    if found is None:
        raise ToolError(f"Parametric setup {args.parametric_name!r} not found")
    variations = found.variations if hasattr(found, "variations") else []
    files: list[str] = []
    summary = {"count": len(variations), "first_5": list(variations[:5])}
    if args.write_csv:
        from .results import _out_path  # local import to avoid cycles
        path = _out_path(f"param_variations_{args.parametric_name}", "csv")
        try:
            c.post.export_parametric_results(args.parametric_name, path)
            files.append(path)
            summary["csv"] = path
        except Exception as exc:
            logger.warning("export_parametric_results failed: %s", exc)
    return ok(summary, files=files).payload