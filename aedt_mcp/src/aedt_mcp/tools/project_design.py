"""Project / design lifecycle tools."""

from __future__ import annotations

import logging
from typing import Any

from ..pyansys_api import ToolError, handle_errors, ok
from ..schemas import (
    CloseProjectArgs,
    ListDesignsArgs,
    OpenDesignArgs,
    SaveProjectArgs,
)
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.project_design")


@handle_errors
def open_design(args: OpenDesignArgs) -> dict[str, Any]:
    """Open (or create) a project/design of the given type and mark it active."""
    client = SESSION.get_or_create(args.design_type, args.project, args.design)
    payload = {
        "design_type": args.design_type,
        "project_name": client.project_name,
        "design_name": client.design_name,
        "desktop_version": SESSION.launch_params.get("version"),
        "registered_designs": SESSION.list_designs(),
    }
    return ok(payload).payload


@handle_errors
def list_designs(_args: ListDesignsArgs) -> dict[str, Any]:
    return {"designs": SESSION.list_designs()}


@handle_errors
def save_project(args: SaveProjectArgs) -> dict[str, Any]:
    """Save the active project (optionally to a full path)."""
    # Pick a registered client that matches the requested project, preferring
    # the most recently active one.
    candidates = SESSION.list_designs()
    client = None
    if args.project:
        for c in (SESSION._designs[k] for k in SESSION._designs if k[0] == args.project):
            client = c
            break
    if client is None and candidates:
        client = SESSION._designs[next(iter(SESSION._designs))]
    if client is None:
        raise ToolError("No active project to save.")
    if args.path:
        client.save_project(file_name=args.path)
        return {"saved_to": args.path, "project": client.project_name}
    client.save_project()
    return {"saved": True, "project": client.project_name}


@handle_errors
def close_project(args: CloseProjectArgs) -> dict[str, Any]:
    """Close the active project, releasing its design clients."""
    closed: list[str] = []
    targets = [k for k in list(SESSION._designs.keys())
               if args.project is None or k[0] == args.project]
    if not targets:
        return {"closed": closed}
    # All designs for one project belong to one project; save it first if asked.
    first = SESSION._designs[targets[0]]
    if args.save:
        first.save_project()
    proj_name = first.project_name
    # Remove all cached designs referencing this project.
    for k in targets:
        closed.append(f"{k[0]}::{k[1]}::{k[2]}")
        SESSION._designs.pop(k, None)
    try:
        # active_design keeps a project handle inside pyaedt's desktop; ask the
        # desktop to close the project.
        SESSION.desktop.close_project(proj_name)
    except Exception as exc:
        logger.warning("close_project desktop call failed: %s", exc)
    if SESSION._active_key in targets:
        SESSION._active_key = next(iter(SESSION._designs), None) and next(iter(SESSION._designs))
    return {"closed": closed, "project": proj_name}