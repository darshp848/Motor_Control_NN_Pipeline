"""Material assignment tools."""

from __future__ import annotations

import logging
from typing import Any

from ..pyansys_api import handle_errors
from ..schemas import AddMaterialArgs, AssignMaterialArgs, ListMaterialsArgs
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.materials")


@handle_errors
def add_material(args: AddMaterialArgs) -> dict[str, Any]:
    """Add a custom material to the active design's material library."""
    client = SESSION.require_active("maxwell3d")
    props: dict[str, Any] = {}
    if args.permittivity is not None:
        props["permittivity"] = args.permittivity
    if args.permeability is not None:
        props["permeability"] = args.permeability
    if args.conductivity is not None:
        props["conductivity"] = args.conductivity
    if args.extra_props:
        props.update(args.extra_props)
    client.materials.add_material(args.name, list(props.keys()) if props else None, **props)
    return {"name": args.name, "properties": props}


@handle_errors
def assign_material(args: AssignMaterialArgs) -> dict[str, Any]:
    client = SESSION.require_active("maxwell3d")
    out = []
    for obj in args.objects:
        try:
            client.assign_material(obj, args.material)
            out.append(obj)
        except Exception:
            try:
                client.modeler[obj].material = args.material
                out.append(obj)
            except Exception:
                raise
    return {"assigned": out, "material": args.material}


@handle_errors
def list_materials(_args: ListMaterialsArgs) -> dict[str, Any]:
    client = SESSION.require_active("maxwell3d")
    try:
        names = [m.name for m in client.materials.materials if hasattr(m, "name")]
    except Exception:
        names = list(client.materials.keys()) if hasattr(client.materials, "keys") else []
    return {"materials": names}