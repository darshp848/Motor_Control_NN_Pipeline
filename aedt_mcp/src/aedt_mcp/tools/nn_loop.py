"""Closed-loop NN training hook.

`run_design_vector` applies a dict of design variables, (re)analyzes a setup,
pulls the requested expressions and returns compact arrays that an online
training client can stream into a CSV. Designed so the LLM (or a Python
client invoked by it) can call this repeatedly to build a motor FEM training
dataset.
"""

from __future__ import annotations

import csv
import logging
import os
from typing import Any

import numpy as np

from ..pyansys_api import ToolError, handle_errors, ok
from ..schemas import RunDesignVectorArgs
from ..session import SESSION

logger = logging.getLogger("aedt_mcp.tools.nn_loop")

OUT_DIR = os.path.abspath(os.environ.get("AEDT_MCP_OUT_DIR", "out"))


@handle_errors
def run_design_vector(args: RunDesignVectorArgs) -> dict[str, Any]:
    """Run one FEM datapoint for NN data collection."""
    c = SESSION.require_active(args.design_type)

    # 1) Apply variables
    for name, value in args.variables.items():
        c[name] = value

    # 2) Analyze the named setup (blocking so we have results when we return)
    c.analyze_setup(args.setup, blocking=True)

    # 3) Pull solution data
    sol = c.post.get_solution_data(
        expressions=args.expressions,
        setup_sweep_name=args.setup,
        primary_sweep_variable=args.primary_sweep,
    )
    if not sol:
        raise ToolError("No solution data returned after analyze. Check setup name and that the solve finished.")

    # 4) Pack payload
    response: dict[str, Any] = {
        "design_type": args.design_type,
        "design": c.design_name,
        "setup": args.setup,
        "variables": args.variables,
        "primary_sweep": args.primary_sweep,
    }
    arrays: dict[str, list[float]] = {}
    files: list[str] = []

    for expr in args.expressions:
        try:
            sweeps, values = sol.get_expression_data(expr)
            sweeps = np.asarray(sweeps).flatten().astype(float)
            values = np.asarray(values).flatten().astype(float)
            arrays[expr] = values.tolist()
            response.setdefault("sweeps", sweeps.tolist())
        except Exception as exc:
            arrays[expr] = []
            response.setdefault("errors", {})[expr] = f"{exc}"

    response["data"] = arrays
    response["nsamples"] = len(arrays.get(args.expressions[0], []))

    if args.append_csv:
        os.makedirs(OUT_DIR, exist_ok=True)
        path = args.append_csv if os.path.isabs(args.append_csv) else os.path.join(OUT_DIR, args.append_csv)
        write_header = not os.path.exists(path)
        with open(path, "a", newline="") as fh:
            writer = csv.writer(fh)
            if write_header:
                header = list(args.variables.keys()) + [args.primary_sweep] + args.expressions
                writer.writerow(header)
            n = response["nsamples"]
            if n == 0:
                row = list(args.variables.values()) + ["-"] + ["-"] * len(args.expressions)
                writer.writerow(row)
            else:
                sweeps = response.get("sweeps", [None] * n)
                for i in range(n):
                    row = list(args.variables.values()) + [sweeps[i]] + [arrays[expr][i] for expr in args.expressions]
                    writer.writerow(row)
        files.append(path)
        response["csv"] = path

    return ok(response, files=files).payload