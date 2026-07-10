"""Design / project variable tools."""

from __future__ import annotations

from typing import Any

from ..pyansys_api import handle_errors
from ..schemas import ListVariablesArgs, SetVariableArgs
from ..session import SESSION


@handle_errors
def set_variable(args: SetVariableArgs) -> dict[str, Any]:
    """Set a design (`name`) or project (`$name`) variable.

    Variables prefixed with `$` are project-level; all others are design-level.
    `name` is the variable name to set/overwrite.
    `expression` is a string expression like ``'1mm'`` or a numeric literal.
    """
    # Pick design containing the variable: project var lives on the desktop
    # project handle; design var lives on whichever design is "active".
    if args.name.startswith("$"):
        var_name = args.name[1:]
        d = SESSION.desktop
        try:
            d.set_app_prop(var_name, args.expression)
        except Exception:
            d.active_design.set_variable(var_name, args.expression)
        return {"name": args.name, "value": args.expression, "scope": "project"}
    # Design variable - apply to the currently active design (prefer maxwell3d
    # then hfss) so the variable exists for downstream setup calls.
    for design_type in ("maxwell3d", "hfss"):
        client = SESSION.active_for(design_type)
        if client is not None:
            client[args.name] = args.expression
            return {"name": args.name, "value": args.expression, "scope": "design",
                    "design": client.design_name}
    raise RuntimeError("No active design to set a design variable on. "
                       "Call open_design first.")


@handle_errors
def list_variables(args: ListVariablesArgs) -> dict[str, Any]:
    client = SESSION.require_active(args.design_type)
    return {
        "design_variables": dict(client.variable_manager.design_variables)
        if hasattr(client.variable_manager, "design_variables") else {},
        "project_variables": dict(client.variable_manager.project_variables)
        if hasattr(client.variable_manager, "project_variables") else {},
    }