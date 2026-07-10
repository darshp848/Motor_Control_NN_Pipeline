"""Field export / sampling tools (Maxwell + HFSS).

Sampling B-field along a polyline contour and exporting field on a volume
are key for motor NN training data (input features = geometry param + current
+ angle; output = field samples along rotor/stator arcs).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import numpy as np

from ..pyansys_api import ToolError, handle_errors, ok
from ..schemas import (
    ExportFieldVolumeArgs,
    FieldCalculatorEvalArgs,
    GetFieldPointsOnContourArgs,
)
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.fields")

OUT_DIR = os.path.abspath(os.environ.get("AEDT_MCP_OUT_DIR", "out"))


def _client(design_type: str):
    return SESSION.require_active(design_type)


def _out_path(basename: str, ext: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(OUT_DIR, f"{basename}_{ts}.{ext}")


@handle_errors
def get_field_points_on_contour(args: GetFieldPointsOnContourArgs) -> dict[str, Any]:
    """Sample a field quantity along a named polyline in the active design.

    Returns summary (length + first/last values) and writes an .npy file
    containing stacked (s, value) pairs where `s` is arc length along the line.
    """
    c = _client(args.design_type)
    field_name = args.field
    quantity = args.quantity
    setup = args.setup or (c.setup_names[0] if c.setup_names else None)
    path = _out_path(f"field_{field_name}_{quantity}_{args.polyline_name}", "npy")

    # PyAEDT field calculator approach: build a named quantity and export it
    # along the polyline. If quantitys export fails, fall back to scalar probe
    # along the polyline vertices via get_scalar_field_value.
    try:
        c.post.export_field_file_on_grid(
            output_file=path.replace(".npy", ".csv"),
            obj_list=None,
            point_count=101,
            field_type=field_name,
            inset=0,
            line_name=args.polyline_name,
            setup=setup,
        )
        files = [path.replace(".npy", ".csv")]
        try:
            data = np.loadtxt(files[0], delimiter=",", skiprows=1)
        except Exception:
            data = np.empty((0, 2))
        np.save(path, data)
        files.append(path)
        summary: dict[str, Any] = {
            "polyline": args.polyline_name,
            "field": field_name,
            "quantity": quantity,
            "setup": setup,
            "samples": int(data.shape[0]),
            "npy": path,
            "csv": files[0],
        }
        return ok(summary, files=files).payload
    except Exception as exc:
        logger.warning("export_field_file_on_grid fallback to scalar probe: %s", exc)

    # Fallback: scalar probe along polyline vertex list
    try:
        verts = c.modeler[args.polyline_name].vertices
    except Exception as exc:
        raise ToolError(
            f"Could not retrieve vertices for polyline {args.polyline_name!r}: {exc}") from exc
    pts = np.array([[v.position[0], v.position[1], v.position[2]] for v in verts])
    try:
        vals = np.array([c.post.get_scalar_field_value(f"{field_name}{quantity}",
                                                       point=pt.tolist(),
                                                       setup=setup,
                                                       intrinsics={})
                         for pt in pts])
    except Exception as exc:
        raise ToolError(f"Scalar field probe failed: {exc}") from exc
    np.save(path, np.column_stack([np.arange(len(vals)), vals]))
    return ok({"polyline": args.polyline_name, "samples": len(vals), "npy": path},
              files=[path]).payload


@handle_errors
def export_field_on_volume(args: ExportFieldVolumeArgs) -> dict[str, Any]:
    """Export a field quantity on a set of named objects (volume plot)."""
    c = _client(args.design_type)
    setup = args.setup or (c.setup_names[0] if c.setup_names else None)
    path = _out_path(f"fieldvol_{args.field}_{args.quantity}", "npz")
    try:
        c.post.export_field_file(
            output_file=path.replace(".npz", ".aedtplt"),
            obj_list=args.objects,
            field_type=args.field,
            quantity_name=f"{args.field}{args.quantity}",
            intrinsics=None,
            setup=setup,
        )
        files = [path.replace(".npz", ".aedtplt")]
        return ok({"objects": args.objects, "field": args.field, "setup": setup,
                   "file": files[0]}, files=files).payload
    except Exception as exc:
        raise ToolError(f"export_field_file failed: {exc}") from exc


@handle_errors
def field_calculator_eval(args: FieldCalculatorEvalArgs) -> dict[str, Any]:
    """Run a field calculator expression; return its scalar value at nominal solution."""
    c = _client(args.design_type)
    try:
        value = c.post.ofieldsreporter.Calculate(args.expression)
    except Exception as exc:
        raise ToolError(f"field calc eval failed for {args.expression!r}: {exc}") from exc
    return {"expression": args.expression, "value": str(value)}