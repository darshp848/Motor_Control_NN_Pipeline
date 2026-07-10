# AGENTS.md - aedt-mcp

This project is an MCP server exposing Ansys AEDT (HFSS + Maxwell 3D) via PyAnsys for motor FEM and neural-network training data generation.

## Environment

- AEDT 2025R2 Student at `C:/Program Files/ANSYS Inc/ANSYS Student/v252`
- Python interpreters on this machine (both verified working):
  - `python` -> **Python 3.13** (default; gets `python -m aedt_mcp`)
  - `py -V:3.11` / `C:\Users\darsh\AppData\Local\Programs\Python\Python311\python.exe` -> Python 3.11
  - `pip` (the pip.exe on PATH) targets Python 3.11; use `python -m pip` for 3.13.
  - Dependencies installed into BOTH 3.11 and 3.13 site-packages.
- PyAEDT 1.2.0 namespace: `from ansys.aedt.core import Desktop, Hfss, Maxwell3d`
  (NOT `import pyaedt` - the legacy name was removed in 1.0.)
- Desktop launch args used by this server: `version="2025.2", non_graphical=True, student_version=True, close_on_exit=False`

## Build / install

```pwsh
cd "C:\Users\darsh\TAMU\IMPI lab\aedt-mcp"
# Editable install into the default `python` (3.13) and 3.11:
python -m pip install -e . --no-deps
py -V:3.11 -m pip install -e . --no-deps
# Runtime + dev deps (already installed but rerun if pyproject changes):
python -m pip install "mcp>=1.2.0" "pyaedt>=1.0.0" "pydantic>=2.5" "numpy>=1.26" "ruff>=0.6" "mypy>=1.10" "pytest>=8.0"
py -V:3.11 -m pip install "mcp>=1.2.0" "pyaedt>=1.0.0" "pydantic>=2.5" "numpy>=1.26" "ruff>=0.6" "mypy>=1.10" "pytest>=8.0"
```

## Lint / typecheck (run after editing source)

```pwsh
python -m ruff check .
python -m mypy --ignore-missing-imports src
```

(Use `py -V:3.11` instead of `python` if you're targeting the 3.11 interpreter.)
Use either of these in this project - both interpreters have the same deps installed.

Run both before declaring a task complete. Fix all lint errors. Ignore mypy `attr-defined` / `call-arg` / `union-attr` for `pyaedt` stubs.

## Smoke (no AEDT launch)

```pwsh
python -m aedt_mcp --help
```

Should print usage and exit 0 without launching AEDT (the FastMCP server is only
imported lazily, and the Desktop is only launched on the first `tools/call`).

## Run server (stdio)

```pwsh
python -m aedt_mcp
```

## Tests

```pwsh
pytest -q
```

Schema validation tests live in `tests/test_schemas.py` and do not require AEDT.

## Architecture notes

- `src/aedt_mcp/session.py`: `AedtSession` singleton - lazily launches `Desktop` on first tool call, holds it for the opencode session.
- `src/aedt_mcp/pyansys_api.py`: thin wrappers that convert `pyaedt` exceptions to `ToolError`.
- `src/aedt_mcp/schemas.py`: pydantic models for every tool's args.
- `src/aedt_mcp/tools/*.py`: FastMCP `@server.tool` registrations grouped by capability.
- `src/aedt_mcp/server.py`: aggregates all tools into one FastMCP server.
- `src/aedt_mcp/__main__.py`: parses `--help`, runs stdio transport.

## Output directory

Numeric datasets and field exports are written to `out/` (relative to the working dir where the server is launched - usually the `aedt-mcp/` project dir). Tool responses carry summary JSON + absolute path to the generated file.