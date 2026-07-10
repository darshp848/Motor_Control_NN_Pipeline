"""Command-line entrypoint: `python -m aedt_mcp` runs the stdio server.

`python -m aedt_mcp --help` exits 0 without launching AEDT.
"""

from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aedt-mcp",
        description=(
            "MCP server exposing Ansys AEDT (HFSS + Maxwell 3D) via PyAnsys "
            "for motor FEM and NN training data generation. AEDT is launched "
            "lazily on the first tool call."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport (default stdio).",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Server log level.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # Import lazily so `--help` does not import pyaedt at all.
    from .server import run

    if args.transport != "stdio":
        # Import fast so the user sees the failure early if deps missing.
        from .session import SESSION  # noqa: F401
    run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())