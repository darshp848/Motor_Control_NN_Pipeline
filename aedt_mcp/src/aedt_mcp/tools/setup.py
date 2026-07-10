"""Setup creation/edition/deletion (Maxwell + HFSS)."""

from __future__ import annotations

import logging
from typing import Any

from ..pyansys_api import ToolError, handle_errors
from ..schemas import CreateSetupArgs, DeleteSetupArgs, EditSetupArgs
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.setup")


def _client(design_type: str):
    return SESSION.require_active(design_type)


@handle_errors
def create_setup(args: CreateSetupArgs) -> dict[str, Any]:
    """Create an analysis setup on the active design.

    For Maxwell3d, `setup_type` is one of:
      "Magnetostatic", "EddyCurrent", "Transient", "Electrostatic", "DCConduction".
    For HFSS, `setup_type` is "HFSSDrivenDefault" (or "HFSSSBRDefault").
    """
    c = _client(args.design_type)
    props: dict[str, Any] = dict(args.additional_props or {})
    if args.design_type == "maxwell3d":
        if args.setup_type.lower() == "transient":
            if args.stop_time is not None:
                props["StopTime"] = args.stop_time
            if args.time_step is not None:
                props["TimeStep"] = args.time_step
            props.setdefault("SaveFieldsType", "Every Step" if args.save_fields else "None")
        props.setdefault("MaximumPasses", args.max_passes)
        props.setdefault("MinimumPasses", args.minimum_converged_passes)
        props.setdefault("PercentError", args.energy_error)
        setup = c.create_setup(name=args.name, setup_type=args.setup_type, **props)
    else:
        # HFSS
        if args.setup_type.lower().startswith("hfss"):
            stype = args.setup_type
        else:
            stype = "HFSSDrivenDefault"
        props.setdefault("MaximumNumberOfPasses", args.max_passes_hfss)
        props.setdefault("MinimumConvergedPasses", args.minimum_converged_passes)
        setup = c.create_setup(name=args.name, setup_type=stype, **props)
    return {"setup_name": getattr(setup, "name", args.name), "setup_type": args.setup_type,
            "design_type": args.design_type}


@handle_errors
def edit_setup(args: EditSetupArgs) -> dict[str, Any]:
    c = _client(args.design_type)
    setup = c.get_setup(args.name)
    if setup is None:
        raise ToolError(f"Setup {args.name!r} not found in active {args.design_type} design")
    for k, v in args.props.items():
        try:
            setup.props[k] = v
        except Exception:
            logger.warning("Could not set %s=%s on setup %s", k, v, args.name)
    setup.update()
    return {"setup_name": args.name, "updated_props": list(args.props.keys())}


@handle_errors
def delete_setup(args: DeleteSetupArgs) -> dict[str, Any]:
    c = _client(args.design_type)
    ok_flag = c.delete_setup(args.name)
    return {"deleted": bool(ok_flag), "setup_name": args.name}