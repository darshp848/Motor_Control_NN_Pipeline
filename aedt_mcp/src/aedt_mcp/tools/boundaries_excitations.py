"""Boundaries, excitations and motion (Maxwell)."""

from __future__ import annotations

import logging
from typing import Any

from ..pyansys_api import ToolError, handle_errors
from ..schemas import (
    AssignCurrentArgs,
    AssignMagnetizationArgs,
    AssignRotateMotionArgs,
    AssignVoltageArgs,
    CreateBoundaryDependentArgs,
    CreateCoilArgs,
    CreateWindingArgs,
)
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.boundaries_excitations")


def _m():
    """Return active Maxwell3d client (raise if none)."""
    return SESSION.require_active("maxwell3d")


@handle_errors
def create_coil(args: CreateCoilArgs) -> dict[str, Any]:
    """Assign a coil terminal to a conductor object."""
    m = _m()
    polarity = "Positive" if args.polarity == "positive" else "Negative"
    coil = m.assign_coil(
        assignment=[args.object_name],
        conductors_number=args.number_of_conductors,
        polarity=polarity,
        name=args.coil_name,
    )
    return {"coil_name": getattr(coil, "name", args.coil_name),
            "object": args.object_name, "type": args.coil_type}


@handle_errors
def create_winding(args: CreateWindingArgs) -> dict[str, Any]:
    """Create a winding (current/voltage source) and attach coils in `objects`."""
    m = _m()
    winding_type = {"current": "Current", "voltage": "Voltage", "external": "External"}[args.winding_type]
    current = float(args.value) if isinstance(args.value, (int, float)) else None
    voltage = float(args.value) if isinstance(args.value, (int, float)) else None
    winding = m.assign_winding(
        assignment=args.objects,
        winding_type=winding_type,
        is_solid=False,
        current=current if current is not None and winding_type == "Current" else 1,
        voltage=voltage if voltage is not None and winding_type == "Voltage" else 0,
        name=args.name,
    )
    w_name = getattr(winding, "name", args.name)
    return {"winding_name": w_name, "type": winding_type, "objects": args.objects,
            "is_winding": args.is_winding}


@handle_errors
def assign_current(args: AssignCurrentArgs) -> dict[str, Any]:
    m = _m()
    b = m.assign_current(
        assignment=list(args.objects),
        amplitude=args.current,
        name=args.name,
        solid=True,
    )
    return {"name": getattr(b, "name", args.name), "current": args.current, "objects": args.objects}


@handle_errors
def assign_voltage(args: AssignVoltageArgs) -> dict[str, Any]:
    m = _m()
    b = m.assign_voltage(assignment=list(args.objects), amplitude=float(args.voltage), name=args.name)
    return {"name": getattr(b, "name", args.name), "voltage": args.voltage, "objects": args.objects}


@handle_errors
def assign_magnetization(args: AssignMagnetizationArgs) -> dict[str, Any]:
    if len(args.direction) not in (0, 3):
        raise ToolError("direction must have 3 entries")
    m = _m()
    # PyAEDT exposes magnetization through assign_magnetization on the Maxwell3d
    # client; if absent on this version, we fall back to setting the material
    # property `magnetic_coercivity` + direction on the object's material.
    if hasattr(m, "assign_magnetization"):
        b = m.assign_magnetization(
            assignment=[args.object_name],
            magnitude=args.magnitude,
            dir_vector=list(args.direction),
            name=args.name,
        )
        return {"name": getattr(b, "name", args.name), "object": args.object_name,
                "magnitude_T": args.magnitude}
    # Fallback path - configure material as permanent magnet.
    mat = m.get_object_material_properties(args.object_name)
    mat_name = (mat or {}).get(args.object_name, [None])[0]
    if mat_name is None:
        raise ToolError(f"Object {args.object_name!r} has no material to set magnetization on.")
    material = m.materials[mat_name]
    material.set_magnetic_coercivity(args.magnitude, list(args.direction))
    return {"name": args.name, "object": args.object_name, "material": mat_name,
            "coercivity_T": args.magnitude}


@handle_errors
def assign_rotate_motion(args: AssignRotateMotionArgs) -> dict[str, Any]:
    """Assign rotational motion to the rotor band region (rotating machine)."""
    m = _m()
    has_limits = args.motion_type != "continuous"
    b = m.assign_rotate_motion(
        assignment=args.rotor_band_object,
        axis="Z",
        positive_movement=args.positive,
        start_position=args.initial_angle_deg,
        has_rotation_limits=has_limits,
        positive_limit=360 if has_limits else 360,
        negative_limit=0,
        angular_velocity=f"{args.angular_velocity_rpm}rpm",
        mechanical_transient=False,
        name=args.name,
    )
    return {"name": getattr(b, "name", args.name), "axis": "Z",
            "omega_rpm": args.angular_velocity_rpm, "band": args.rotor_band_object}


@handle_errors
def create_boundary_dependent(args: CreateBoundaryDependentArgs) -> dict[str, Any]:
    """Create a master/dependent (symmetry) boundary on a list of faces."""
    m = _m()
    if args.master:
        b = m.assign_symmetry(assignment=list(args.faces), symmetry_name=args.name, is_odd=True)
        return {"name": args.name, "kind": "master", "faces": args.faces, "ok": bool(b)}
    b = m.assign_symmetry(assignment=list(args.faces), symmetry_name=args.name + "_dep", is_odd=True)
    return {"name": args.name + "_dep", "kind": "dependent", "faces": args.faces, "ok": bool(b)}