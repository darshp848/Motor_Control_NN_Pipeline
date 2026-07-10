"""Modeler / geometry primitive tools."""

from __future__ import annotations

import logging
from typing import Any

from ..pyansys_api import ToolError, handle_errors
from ..schemas import (
    BooleanArgs,
    CreateBoxArgs,
    CreateCircleArgs,
    CreateCylinderArgs,
    CreatePolylineArgs,
    CreateRectangleArgs,
    DuplicateAlongLineArgs,
    DuplicateAroundAxisArgs,
    ImportGeometryArgs,
    MoveTranslateArgs,
    RotateArgs,
)
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.modeler")


def _client(design_type: str):
    return SESSION.require_active(design_type)


@handle_errors
def create_box(args: CreateBoxArgs) -> dict[str, Any]:
    """Create a 3D box at `position` with the given `sizes`."""
    if len(args.position) != 3:
        raise ToolError("position must have 3 entries")
    if len(args.sizes) != 3:
        raise ToolError("sizes must have 3 entries")
    client = _client("maxwell3d")
    box = client.modeler.create_box(position=args.position, sizes=list(args.sizes), name=args.name)
    if args.material:
        client.assign_material(box, args.material)
    return {"name": box.name, "id": box.id, "material": args.material or None}


@handle_errors
def create_cylinder(args: CreateCylinderArgs) -> dict[str, Any]:
    if len(args.center) != 3:
        raise ToolError("center must have 3 entries")
    client = _client("maxwell3d")
    obj = client.modeler.create_cylinder(
        cs_axis=args.axis,
        position=list(args.center),
        radius=args.radius,
        height=args.height,
        num_sides=0,
        name=args.name,
    )
    if args.material:
        client.assign_material(obj, args.material)
    return {"name": obj.name, "id": obj.id, "material": args.material or None}


@handle_errors
def create_circle(args: CreateCircleArgs) -> dict[str, Any]:
    if len(args.center) != 3:
        raise ToolError("center must have 3 entries")
    client = _client("maxwell3d")
    obj = client.modeler.create_circle(
        cs_plane=args.plane,
        position=list(args.center),
        radius=args.radius,
        name=args.name,
    )
    return {"name": obj.name, "id": obj.id}


@handle_errors
def create_rectangle(args: CreateRectangleArgs) -> dict[str, Any]:
    if len(args.position) != 3 or len(args.sizes) != 2:
        raise ToolError("position must be 3, sizes must be 2")
    client = _client("maxwell3d")
    obj = client.modeler.create_rectangle(
        cs_plane=args.plane,
        position=list(args.position),
        size=list(args.sizes),
        name=args.name,
    )
    return {"name": obj.name, "id": obj.id}


@handle_errors
def create_polyline(args: CreatePolylineArgs) -> dict[str, Any]:
    points = [(float(args.points[i]), float(args.points[i + 1]), float(args.points[i + 2]))
              for i in range(0, len(args.points), 3)]
    client = _client("maxwell3d")
    obj = client.modeler.create_polyline(points, name=args.name, closed=args.close)
    return {"name": obj.name, "id": obj.id}


@handle_errors
def boolean_op(args: BooleanArgs) -> dict[str, Any]:
    client = _client("maxwell3d")
    m = client.modeler
    if args.operation == "unite":
        res = m.unite(args.object_list, keep_originals=args.keep_originals)
    elif args.operation == "intersect":
        lst = args.object_list + (args.tool_list or [])
        res = m.intersect(lst, keep_originals=args.keep_originals)
    elif args.operation == "subtract":
        if not args.tool_list:
            raise ToolError("subtract requires tool_list")
        res = m.subtract(args.object_list, args.tool_list, keep_originals=args.keep_originals)
    else:
        raise ToolError(f"unknown op {args.operation!r}")
    return {"result": getattr(res, "name", str(res)), "operation": args.operation}


@handle_errors
def duplicate_around_axis(args: DuplicateAroundAxisArgs) -> dict[str, Any]:
    client = _client("maxwell3d")
    new_objs = client.modeler.duplicate_around_axis(
        objid=args.object_name,
        cs_axis=args.axis,
        angle=args.angle,
        nclones=args.count,
        is_3d_comp=False,
    )
    # pyaedt returns ([obj_ids], [new_names]) tuple
    names: list[str] = []
    if isinstance(new_objs, tuple) and len(new_objs) == 2:
        names = list(new_objs[1])
    else:
        names = [str(x) for x in new_objs]
    return {"created": names, "source": args.object_name, "count": args.count}


@handle_errors
def duplicate_along_line(args: DuplicateAlongLineArgs) -> dict[str, Any]:
    if len(args.vector) != 3:
        raise ToolError("vector must have 3 entries")
    client = _client("maxwell3d")
    new_objs, names = client.modeler.duplicate_along_line(
        objid=args.object_name,
        vector=list(args.vector),
        nclones=args.count,
        is_3d_comp=False,
    )
    return {"created": list(names), "source": args.object_name, "count": args.count}


@handle_errors
def move_translate(args: MoveTranslateArgs) -> dict[str, Any]:
    if len(args.vector) != 3:
        raise ToolError("vector must have 3 entries")
    client = _client("maxwell3d")
    client.modeler.move(args.object_names, vector=list(args.vector))
    return {"objects": args.object_names, "moved": True}


@handle_errors
def rotate(args: RotateArgs) -> dict[str, Any]:
    client = _client("maxwell3d")
    client.modeler.rotate(args.object_names, axis=args.axis, angle=args.angle_deg)
    return {"objects": args.object_names, "rotated_deg": args.angle_deg}


@handle_errors
def import_geometry(args: ImportGeometryArgs) -> dict[str, Any]:
    client = _client("maxwell3d")
    imported = client.modeler.import_3d_cad(args.path)
    name = args.name or (imported[0].name if isinstance(imported, list) and imported else "imported")
    return {"path": args.path, "imported_name": name}


@handle_errors
def delete_objects(_args: dict[str, Any] | None = None) -> dict[str, Any]:
    # Convenience tool; the LLM should pass an object_list argument.
    raise ToolError("delete_objects is not registered; use the modeler API directly via create_* + boolean_op, "
                    "or extend this module. Argument: object_list=[\"name1\", ...].")