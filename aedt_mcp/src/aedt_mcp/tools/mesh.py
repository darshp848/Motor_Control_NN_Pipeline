"""Mesh control tools."""

from __future__ import annotations

import logging
from typing import Any

from ..pyansys_api import handle_errors
from ..schemas import AssignLengthMeshArgs, AssignSkinDepthMeshArgs, SurfaceMeshArgs
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.mesh")


def _client():
    return SESSION.require_active("maxwell3d")


@handle_errors
def assign_length_mesh(args: AssignLengthMeshArgs) -> dict[str, Any]:
    """Length-based mesh refinement on the given objects."""
    c = _client()
    op = c.mesh.assign_length_mesh(
        objects=args.objects,
        max_length=args.max_length,
        name=args.name,
    )
    return {"name": getattr(op, "name", args.name), "objects": args.objects,
            "max_length": args.max_length}


@handle_errors
def assign_skin_depth_mesh(args: AssignSkinDepthMeshArgs) -> dict[str, Any]:
    c = _client()
    op = c.mesh.assign_skin_depth_mesh(
        objects=args.objects,
        skin_depth=args.skin_depth,
        name=args.name,
    )
    return {"name": getattr(op, "name", args.name), "skin_depth": args.skin_depth}


@handle_errors
def surface_mesh(args: SurfaceMeshArgs) -> dict[str, Any]:
    """Limit number of elements on selected faces (surface mesh length)."""
    c = _client()
    op = c.mesh.assign_surf_mesh_on_faces(args.faces, elements=args.num_elements, name=args.name)
    return {"name": getattr(op, "name", args.name), "faces": args.faces}