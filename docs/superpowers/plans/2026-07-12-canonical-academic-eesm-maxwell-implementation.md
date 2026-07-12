# Canonical Academic EESM Maxwell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan in the current session. Use Computer Use for every AEDT GUI action. Work only in the primary checkout; do not create or use Git worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and qualify the approved 10 kW, 4-pole academic EESM as a Maxwell 2-D Magnetostatic model, then unblock Task 9 only if every Task 8 gate passes.

**Architecture:** A narrow IronPython-compatible GUI-run builder owns deterministic AEDT object creation and writes machine-readable status. Computer Use runs and inspects that script in AEDT. The existing Task 8 exporter, normalizer, and qualifier own the four-point smoke, eight-point pilot, and fail-closed release decision.

**Tech Stack:** AEDT Student 2025 R2, Maxwell 2-D Magnetostatic, IronPython 2.7-style GUI scripts, Python 3.11 offline normalization, CSV/JSON, pytest.

## Global constraints

- Primary checkout only: `C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline`; no worktrees.
- Authoritative geometry spec: `docs/superpowers/specs/2026-07-12-canonical-academic-eesm-geometry-design.md`.
- Target project: `aedt_mcp/tmp/aedt_projects/eesm_qual/eesm_qual.aedt`.
- Target design/setup: `EESM_2D_Qual`, `Setup_Qual`, `Setup_Qual : LastAdaptive`.
- Do not open the IPM project in a second AEDT instance and do not modify it.
- Use Computer Use for AEDT; do not launch, attach, or drive AEDT from PowerShell or PyAEDT.
- Builder scripts run only through AEDT **Automation -> Run Script** and always write JSON status, including failure.
- Do not run a solve until geometry/material/winding/boundary/setup validation is recorded.
- Do not run more than the four-point smoke until its evidence is reviewed.
- Do not start Task 9 unless `qualification_report.json` is `pass` and every required artifact exists.
- Reuse the existing four collected cases in `eesm/tests/test_maxwell_adapter.py`; add no new collected cases.
- AEDT Student final mesh must contain 800-1,950 triangles and at least two effective elements across the 0.6 mm air gap.

---

### Task 1: Create the deterministic AEDT model builder

**Files:**
- Create: `eesm/aedt/build_canonical_eesm.py`
- Modify: `eesm/docs/MAXWELL_EESM_QUALIFICATION.md`
- Modify: `eesm/tests/test_maxwell_adapter.py` only by adding assertions inside the existing `valid` parameterized case

**Interfaces:**
- Produces `eesm/aedt/eesm_model_build_status.json`.
- Creates project/design objects with the exact names frozen by the spec.
- Does not solve or export FEM results.

- [ ] **Step 1: Extend the existing source-contract case without adding a collected test**

Inside the existing `test_adapter_contract` function, only for `variant == "valid"`, read `build_canonical_eesm.py` and assert these safety strings exist:

```python
builder = (AEDT_DIR / "build_canonical_eesm.py").read_text(encoding="utf-8")
assert 'DESIGN_NAME = "EESM_2D_Qual"' in builder
assert 'SETUP_NAME = "Setup_Qual"' in builder
assert 'OUT_JSON = os.path.join(ROOT, "eesm_model_build_status.json")' in builder
assert '"solve_attempted": False' in builder
assert "M270-35A" in builder
```

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest eesm/tests/test_maxwell_adapter.py -q
```

Expected: the same four collected cases, with the valid case failing because the builder is absent.

- [ ] **Step 2: Implement the safe GUI-run script shell**

Use only `json`, `math`, `os`, and `traceback`. Define:

```python
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(ROOT, "eesm_model_build_status.json")
PROJECT_NAME = "eesm_qual"
DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"
STEEL_NAME = "M270-35A"
MODEL_DEPTH = "120mm"
```

Reuse the established `normalize`, `call`, `required`, `warn`, and
always-write-status pattern from `export_eesm_points.py`. Initialize status as:

```python
payload = {
    "status": "running",
    "solve_attempted": False,
    "project": PROJECT_NAME,
    "design": DESIGN_NAME,
    "setup": SETUP_NAME,
    "checks": {},
}
```

The final `finally` block must serialize `normalize(payload)` and display its
path through `AddWarningMessage`.

- [ ] **Step 3: Create or rebuild only the owned Maxwell design**

Activate `eesm_qual` with `oDesktop.SetActiveProject(PROJECT_NAME)`. If
`EESM_2D_Qual` already exists, delete that design only after confirming its
name exactly; never delete another design or project. Insert a Maxwell 2-D
design with solution type `Magnetostatic`, activate it, set XY geometry mode,
and set model depth to 120 mm.

Create local variables with exact expressions:

```text
Id = 0A
Iq = 0A
If = 0A
theta_e = 0deg
Ia = Id
Ib = -0.5*Id + 0.866025403784*Iq
Ic = -0.5*Id - 0.866025403784*Iq
```

Record each variable name/expression in `payload["variables"]`.

- [ ] **Step 4: Build the frozen geometry deterministically**

Use `Modeler.CreateCircle`, `CreateRectangle`, `CreatePolyline`,
`DuplicateAroundAxis`, `Subtract`, and `Unite` with millimetre coordinates.
Create these named object groups:

```text
Region, StatorCore, RotorCore, Shaft,
Slot_01..Slot_24,
StatorCoil_01_Top..StatorCoil_24_Top,
StatorCoil_01_Bottom..StatorCoil_24_Bottom,
FieldCoil_P1_Pos, FieldCoil_P1_Neg, ... FieldCoil_P4_Pos, FieldCoil_P4_Neg
```

Required construction values come verbatim from the spec:

```text
stator OD/bore = 180/110 mm
rotor OD = 108.8 mm
shaft OD = 40 mm
slot center offset/pitch = 7.5/15 mechanical degrees
slot opening/depth/body width = 2/20/7 mm
rotor hub radius = 34 mm
pole body = radius 34..49 mm, width 20 mm
pole shoe = radius 49..54.4 mm, arc 58.5 degrees
field window = radius 36..47 mm, 7 mm per side
region radius = 135 mm
```

Subtract all slots and stator coil regions from `StatorCore`; keep coil objects
as separate copper regions. Unite hub, pole bodies, and pole shoes into
`RotorCore`. Do not add fillets in the first build.

- [ ] **Step 5: Assign materials, windings, boundary, torque, and setup**

Fail if `M270-35A` is unavailable. Assign it to `StatorCore` and `RotorCore`,
copper to all coil objects, nonmagnetic stainless steel to `Shaft`, and vacuum
to `Region`.

Create winding groups `PhaseA`, `PhaseB`, `PhaseC`, and `Field`. Assign coil
sides according to the exact phase-belt table in the spec, with 36 phase turns
and alternating field-pole polarity at 80 turns per pole. Excitations reference
`Ia`, `Ib`, `Ic`, and `If`.

Assign vector-potential zero to the exterior edge of `Region`. Create torque
parameter `TorqueRotor` on `RotorCore`, all field coils, and `Shaft`.

Create `Setup_Qual` with:

```text
maximum passes = 8
percent error = 1
minimum passes = 2
minimum converged passes = 1
```

Add local mesh refinement to the air-gap-adjacent stator/rotor edges and pole
shoes. Do not call `Analyze`.

- [ ] **Step 6: Validate and save build evidence**

Call `design.ValidateDesign()` and immediately capture message levels 0-3.
Record object names, material assignments, winding names, setup names,
validation result, and messages. Set status to `built` only if all required
names exist and validation reports no error. Save the project.

Run offline checks:

```powershell
.\.venv\Scripts\python.exe -m py_compile eesm/aedt/build_canonical_eesm.py
.\.venv\Scripts\python.exe -m pytest eesm/tests/test_maxwell_adapter.py -q
```

Expected: compile succeeds and exactly four tests pass.

- [ ] **Step 7: Commit the builder before GUI execution**

```powershell
git add eesm/aedt/build_canonical_eesm.py eesm/docs/MAXWELL_EESM_QUALIFICATION.md eesm/tests/test_maxwell_adapter.py
git commit -m "feat(eesm): add canonical Maxwell model builder"
git push origin eesm-pipeline
```

### Task 2: Build and inspect the model with Computer Use

**Files/evidence:**
- Run: `eesm/aedt/build_canonical_eesm.py`
- Read: `eesm/aedt/eesm_model_build_status.json`
- Save: `aedt_mcp/tmp/aedt_projects/eesm_qual/eesm_qual.aedt`

- [ ] **Step 1: Open the target project and run the builder**

With Computer Use, activate the existing AEDT Student window, select project
`eesm_qual`, then use **Automation -> Run Script** to run the builder from the
primary checkout. Do not accept any prompt that opens `ipm_1.aedt` in a second
instance.

- [ ] **Step 2: Inspect the status before any solve**

Read `eesm_model_build_status.json`. Stop if status is not `built`,
`solve_attempted` is not false, validation contains an error, or any frozen
object/material/winding/setup is missing.

- [ ] **Step 3: Inspect the GUI model**

Use Computer Use to expand the project tree and verify `EESM_2D_Qual`,
`Setup_Qual`, windings, mesh operations, and `TorqueRotor`. Capture the visible
geometry. Do not solve.

- [ ] **Step 4: Generate the initial mesh only**

Use Maxwell's initial-mesh operation without analysis. Record triangle count.
The gate is 800-1,950 triangles and at least two elements across the air gap.
If above 1,950, remove slot-bottom fillets only (the initial build has none) or
reduce noncritical local refinement. Do not change frozen geometry.

### Task 3: Configure evidence extraction and run the four-point smoke

**Files:**
- Modify: `eesm/aedt/export_eesm_points.py`
- Produce: `eesm/aedt/eesm_qualification_export_status.json`
- Produce: `eesm/aedt/eesm_qualification_progress.csv`
- Produce: `eesm/aedt/point_exports/*_flux_abc.csv`

- [ ] **Step 1: Freeze exporter names and add solver-evidence extraction**

Set exactly:

```python
SETUP_NAME = "Setup_Qual"
SOLUTION_NAME = "Setup_Qual : LastAdaptive"
POLE_PAIRS = 2
ROTOR_POSITION_DEG = 0.0
TORQUE_OUTPUT_NAME = "TorqueRotor"
SMOKE_APPROVED = False
```

Remove the static `MESH_ELEMENTS` and `ADAPTIVE_PASSES` configuration gate.
After every successful solve, export actual solver evidence with:

```python
mesh_path = os.path.join(EXPORT_DIR, point["PointName"] + "_meshstats.ms")
conv_path = os.path.join(EXPORT_DIR, point["PointName"] + "_convergence.conv")
required(lambda: design.ExportMeshStats(SETUP_NAME, "", mesh_path, True),
         "Export mesh statistics")
required(lambda: design.ExportConvergence(SETUP_NAME, "", conv_path),
         "Export convergence history")
```

Apply the same missing/empty-file hard failure used for ABC flux exports.
Parse the convergence header by name rather than fixed column position. The
final nonempty data row supplies the final `Triangles` value; the number of
nonempty adaptive data rows supplies `AdaptivePasses`. Require both to be
positive integers, require triangles to be no more than 1,950, and write them
into the raw result row. Preserve both raw evidence files. If AEDT's exported
header lacks a triangle field, stop the smoke and retain the raw files for a
narrow parser correction; never guess the values.

Extend the existing `valid` source-contract assertions to require
`ExportMeshStats`, `ExportConvergence`, and the two evidence filenames. Do not
add a collected test.

- [ ] **Step 2: Review current-variable mutation before running**

Confirm `Id`, `Iq`, and `If` appear under the active design's local variables
and that changing them updates `Ia`, `Ib`, and `Ic`. Record one screenshot or
status payload. If variable mutation or winding current binding is ambiguous,
stop without solving.

- [ ] **Step 3: Run only the smoke**

Use Computer Use and **Automation -> Run Script** to run
`export_eesm_points.py`. The script must process only:

```text
field_only, q_current, negative_d, combined_rated
```

It must stop with `smoke_complete_review_required`, not `complete`.

- [ ] **Step 4: Review smoke evidence**

Require four converged rows, four nonempty ABC flux exports, finite dq flux,
finite torque, positive mesh/pass evidence, understood solver messages, and no
failed progress row. Confirm field excitation increases d-axis flux and q-sign
behavior is explainable. Keep `SMOKE_APPROVED = False` if any check is weak.

### Task 4: Run the remaining pilot and fail-closed qualification

**Files/evidence:**
- Modify: `eesm/aedt/export_eesm_points.py` only to set `SMOKE_APPROVED = True`
- Produce: canonical pilot CSV
- Produce: `qualification_report.json`

- [ ] **Step 1: Approve continuation only from reviewed smoke evidence**

Set `SMOKE_APPROVED = True` only when Task 3 has no failed or inconclusive
evidence. Commit the reviewed constant change before the remaining pilot.

- [ ] **Step 2: Run the remaining four pilot points with Computer Use**

Run the same exporter. Resume must reject any prior failed row and process only
the four unfinished points.

- [ ] **Step 3: Normalize raw results**

```powershell
.\.venv\Scripts\python.exe eesm/aedt/normalize_eesm_results.py `
  eesm/aedt/eesm_qualification_progress.csv `
  eesm/aedt/eesm_qualification_points.csv `
  out/eesm/qualification/canonical_qualification.csv
```

- [ ] **Step 4: Generate the qualification report**

```powershell
.\.venv\Scripts\python.exe eesm/aedt/qualify_eesm_project.py `
  out/eesm/qualification/canonical_qualification.csv `
  out/eesm/qualification/qualification_report.json
```

Expected: exit 0 and `overall_status: pass`. Any `fail`, `inconclusive`,
nonzero exit, missing artifact, or unexplained torque discrepancy blocks Task 9.

- [ ] **Step 5: Run final compatibility verification**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: existing suite passes with no new collected cases beyond the four
already present in `test_maxwell_adapter.py`.

### Task 5: Record the Task 9 gate decision

**Files:**
- Modify: `eesm/docs/MAXWELL_EESM_QUALIFICATION.md`
- Modify: `README.md`
- Modify research-side status documents only if a verified result bundle or
  qualification artifact supports the statement

- [ ] **Step 1: Audit every prerequisite**

Record evidence for geometry revision, material revision, solver revision,
object names, current variables, winding signs, mesh/pass count, eight pilot
rows, raw ABC flux, canonical dq flux, torque, and qualification checks.

- [ ] **Step 2: Decide without override**

If every requirement is proven, record `Task 9 software/campaign start:
unblocked`. Otherwise record `blocked` with the exact failing evidence. Never
hand-edit `qualification_report.json` or weaken a gate.

- [ ] **Step 3: Commit only reviewed source and small evidence metadata**

Do not commit the `.aedtresults` directory, large solver files, temporary
reports, or raw campaign data. Preserve reviewed small JSON/CSV evidence under
`out/eesm/qualification` only if repository policy explicitly permits it.
