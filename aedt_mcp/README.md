# aedt-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes
[Ansys AEDT](https://www.ansys.com/products/electronics) 2025R2 Student
through [PyAnsys (PyAEDT 1.2)](https://aedt.docs.pyansys.com) so an LLM
agent can drive **Maxwell 3D** (motor FEM) and **HFSS** (RF/EMI) simulations,
including a closed-loop hook for neural-network training-data generation.

Designed for the IMPI lab's motor-design workflow (FEM datapoints feeding
ML surrogate models). No MotorCAD dependency is required.

## Quick start

```pwsh
# 1. Install (deps land in both Python 3.11 and 3.13 site-packages on this machine)
cd "C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp"
python -m pip install -e . --no-deps
python -m pip install "mcp>=1.2.0" "pyaedt>=1.0.0" "pydantic>=2.5" "numpy>=1.26"

# 2. Verify it imports and serves without AEDT
python -m aedt_mcp --help

# 3. Lint / tests / typecheck
python -m ruff check .
python -m mypy --ignore-missing-imports src
python -m pytest -q
```

Then point your MCP client at this server. For opencode, use the
`opencode.json` shipped at the repo root:

```json
{
  "mcp": {
    "aedt": {
      "type": "local",
      "command": ["python", "-m", "aedt_mcp"],
      "enabled": true,
      "environment": {
        "ANSYSEM_ROOT": "C:/Program Files/ANSYS Inc/ANSYS Student/v252/AnsysEM"
      }
    }
  }
}
```

For other MCP clients (Claude Desktop, mcphost, etc.), invoke
`python -m aedt_mcp` over **stdio**.

## How it behaves

- AEDT is launched **lazily** on the first `tools/call` and **kept alive**
  for the whole server session. Default launch args target AEDT 2025R2
  Student in non-graphical mode (`version="2025.2", non_graphical=True,
  student_version=True, close_on_exit=False`). Override via env vars:
  - `AEDT_MCP_VERSION` (default `2025.2`)
  - `AEDT_MCP_STUDENT=0/1` (default `1`)
  - `AEDT_MCP_GRAPHICAL=0/1` (default `0` -> non-graphical)
  - `AEDT_MCP_OUT_DIR` (default `./out`)

- Numeric datasets and field exports (`.csv`, `.npy`, `.aedtplt`) are
  written under `out/`. Tool responses carry summary JSON + absolute file
  paths, so downstream Python code can stream them into training pipelines.

- Tool errors surface as MCP `isError: true` with a traceback string; the
  server never crashes the stdio loop.

## Available tools (47)

Grouped by capability (`design_type = "maxwell3d"` for motors; `"hfss"` for RF):

| Group | Tools |
|---|---|
| project/design | `open_design`, `list_designs`, `save_project`, `close_project` |
| modeler | `create_box`, `create_cylinder`, `create_circle`, `create_rectangle`, `create_polyline`, `boolean_op`, `duplicate_around_axis`, `duplicate_along_line`, `move_translate`, `rotate`, `import_geometry` |
| materials | `add_material`, `assign_material`, `list_materials` |
| variables | `set_variable`, `list_variables` |
| boundaries/excitations | `create_coil`, `create_winding`, `assign_current`, `assign_voltage`, `assign_magnetization`, `assign_rotate_motion`, `create_boundary_dependent` |
| mesh | `assign_length_mesh`, `assign_skin_depth_mesh`, `surface_mesh` |
| setup | `create_setup`, `edit_setup`, `delete_setup` |
| solve | `analyze_setup`, `get_solve_status` |
| results / post | `get_solution_data`, `get_torque`, `get_flux_linkage`, `get_winding_inductance` |
| parametric | `create_parametric_setup`, `add_variation`, `analyze_parametric`, `get_variation_table` |
| fields | `get_field_points_on_contour`, `export_field_on_volume`, `field_calculator_eval` |
| nn loop | `run_design_vector` |

### Motor FEM example flow (LLM-driven)

1. `open_design(design_type="maxwell3d", design="bpmm_3kW")`
2. `set_variable(name="current", expression="5A")`,
   `set_variable(name="rpm", expression="1500")`,
   `set_variable(name="theta0", expression="0deg")`
3. `create_cylinder(...)` for stator iron, rotor iron, magnets, windings...
   `boolean_op("subtract", ...)` to cut slots, `duplicate_around_axis(count=pole_count, ...)` for symmetry.
4. `assign_material("rotor_iron", "NdFe37")`, `add_material("PM_N42", permeability=1.05, ...)`,
   `assign_magnetization("magnet_n", magnitude=1.2, direction=[1,0,0])`.
5. `create_coil("coil_a", "CoilA", current_value="5A", polarity="positive", coil_type="stranded", number_of_conductors=N)`
   `create_winding(objects=["CoilA"], name="WdgA", winding_type="current", value="5A")` ...
   `assign_rotate_motion("rotor_band", angular_velocity_rpm="(rpm)")`.
6. `assign_length_mesh(objects=["rotor_band"], max_length="0.5mm")`.
7. `create_setup(setup_type="Transient", stop_time="20ms", time_step="0.5ms", max_passes=10)` then
   `analyze_setup(name="Setup1", block=True)`.
8. `get_torque(torque_name="Torque1")`, `get_flux_linkage(winding="WdgA")`,
   `get_field_points_on_contour(polyline_name="air_gap_arc", field="B", quantity="Mag")`.
9. Loop with `run_design_vector(variables={"current":"3A","theta0":"15deg"}, expressions=["Torque1","FluxLinkage(WdgA)"], append_csv="train.csv")`
   to assemble a full NN training dataset.

## Status / caveats

- Tools are refactor-safe against `pyaedt 1.2.0`'s public API
  (`ansys.aedt.core`). Signatures verified against installed source:
  `Modeler3D.create_box/cylinder/circle/polyline/duplicate_around_axis/...`,
  `Maxwell3d.assign_coil/assign_winding/assign_current/assign_voltage/
  assign_symmetry/assign_rotate_motion/create_setup/analyze_setup`,
  `PostProcessorCommon.get_solution_data/export_report_to_csv`, etc.

- In PyAEDT 1.0+, `import pyaedt` is no longer the supported namespace; use
  `from ansys.aedt.core import ...`.

- `pyaedt[all]` pulls `fpdf2` (LGPLv3); if you're license-sensitive, install
  `aedt-mcp` from the `[no-lgpl]` extra instead of `[all]`.

## License

MIT (this project). PyAEDT is MIT. AEDT itself is Ansys-licensed.
A student-version is required for `student_version=True`; full versions
can swap to `student_version=False` via `AEDT_MCP_STUDENT=0`.