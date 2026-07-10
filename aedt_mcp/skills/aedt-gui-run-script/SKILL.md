---
name: aedt-gui-run-script
description: Create narrow, user-run AEDT 2025 R2 GUI scripts for this motor-control FEM data project. Use when Codex needs to generate or modify Python scripts that the human will run from Ansys Electronics Desktop Student 2025 R2 via Automation -> Run Script, especially ScriptEnv/IronPython-style scripts for project probing, Maxwell2D Magnetostatic solving, ReportSetup table creation, ExportToFile CSV export, and JSON status files under tmp/aedt_jobs. Do not use for PyAEDT-launched automation, headless AEDT control, direct process killing, broad report/context probing, or scripts run outside the AEDT GUI.
---

# AEDT GUI Run Script

Use this skill only to create scripts that the user runs manually inside AEDT:

```text
Automation -> Run Script
```

Last verified run: `2026-07-08 09:47`, `Maxwell2DDesign4 / Setup_MagProbe`
via `tmp/aedt_jobs/gui_probe_magnetostatic_path_result.json` (solve_result 0,
message "Normal completion of simulation on server: Local Machine").

If anything in this skill no longer matches a fresh run, update the
`Last verified run` line above first; do not keep using stale facts.

Target environment:

- AEDT Student 2025 R2 / `2025.2SV`
- GUI script runtime (IronPython 2.7-flavored), not normal CPython
- Project root:
  `C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp`
- Generated scripts live under:
  `tmp\aedt_projects\ipm_1_probe`
- Result JSON/log/CSV files live under:
  `tmp\aedt_jobs`
- History of past runs and failures: `tmp\aedt_jobs/*.json` and the handoff
  log at `AEDT_HANDOFF.md`. Read those before reinventing a wheel.

Per-project config (defaults below are for the `ipm_1` IPM motor). For a
different motor project, copy this skill once per project and change
`PROJECT_NAME`, `DESIGN_NAME`, `SETUP_NAME`, the windings tuple, and the
output job_id prefix. Do NOT hard-code the ipm_1 paths blindly outside
the default project.

## Hard Rules

- Generate one narrow script per task.
- Never launch AEDT, attach PyAEDT, kill processes, or start gRPC from these scripts.
- Never import `pyaedt`, `subprocess`, `pathlib`, or project-local packages.
- Never use `math.isfinite`; IronPython 2.7 does not expose it (it was added
  in CPython 3.2). Use the `is_finite` helper shown below.
- Avoid f-strings, type hints, dataclasses, async, pathlib, and modern CPython-only features.
- Use `os.path`, `json`, `csv`, `math`, and `traceback`.
- Always write a JSON status file, even on failure.
- Always use absolute Windows paths for script outputs.
- Always wrap AEDT API calls with a `call(fn)` helper that captures `ok`,
  `value`, `error`, and a short traceback tail. Catch `BaseException` (not
  `Exception`); IronPython runtime errors such as `IronPythonRuntimeException`
  do not all inherit from `Exception` in the way CPython expects.
- Prefer `AddWarningMessage(...)` at the end so the user sees where the
  result JSON was written.
- Keep scripts idempotent where practical: delete or overwrite only the
  specific report/output the script owns.

  ## File-existence Rule (Hard)

  AEDT may return success from `ExportToFile(...)` without writing a file
  for unsupported expressions or for reports that were not actually
  created. After every `ExportToFile`, the script MUST

  ```python
  if not (os.path.exists(csv_path) and os.path.getsize(csv_path) > 0):
      raise RuntimeError("ExportToFile returned but file missing/empty: " + csv_path)
  ```

  before parsing it. Treat missing-file-after-success as a hard failure,
  not a recoverable one.

## Report-Loop Discipline (Hard)

Broad loops over report types, solution contexts, expressions, or report
creation have crashed AEDT in this project (see `AEDT_HANDOFF.md:44-45`).
If a loop over reports is necessary:

- Cap the loop at 3 iterations of `CreateReport` / `ExportToFile`.
- Abort the entire script on the first iteration that errors.
- Never probe `CreateReport` across multiple `SolutionName` /
  `ContextName` combinations inside one script. Pick one known-good
  solution name (`Setup_MagProbe : LastAdaptive`) and stick to it.

Do not mutate Program Files, OneDrive config, or the original project.
Work only on copied projects under `tmp\aedt_projects`.

## Proven Project Facts

Use these facts unless the current task provides newer evidence. Each
fact is tagged `# PROVEN` (observed working in a logged run) or
`# BROKEN` (observed failing in a logged run) so you can copy-paste with
confidence rather than guessing.

- AEDT Student blocks Maxwell Transient solves `# BROKEN`:
  `Ansys Electronics Desktop Student does not support Maxwell Transient solution`.
- `Maxwell2DDesign3` is a converted transient Maxwell design and must
  not be solved under Student `# BROKEN`.
- `Maxwell2DDesign4` is the copied Student-compatible Magnetostatic
  design `# PROVEN`. It solved successfully with:
  - design type: `Maxwell 2D`
  - solution type: `Magnetostatic`
  - setup: `Setup_MagProbe`
  - solution: `Setup_MagProbe : LastAdaptive`
  - winding groups: `PhaseA`, `PhaseB`, `PhaseC`
- `ReportSetup.ExportToFile(report_name, csv_path)` is proven safe for
  existing/exportable reports `# PROVEN`.
- Exporting these three expressions as a Magnetostatic Data Table `# PROVEN`:
  - `FluxLinkage(PhaseA)`
  - `FluxLinkage(PhaseB)`
  - `FluxLinkage(PhaseC)`
- Example proven exported row (one solve at default currents,
  `AEDT_HANDOFF.md:41-43`):
  `fractions=4`, `FluxLinkage(PhaseA)=0.0155609380613968 Wb`,
  `FluxLinkage(PhaseB)=0.0509523868830839 Wb`,
  `FluxLinkage(PhaseC)=-0.0486271433364105 Wb`.
- Direct export of `I_d`, `I_q`, `Flux_d`, `Flux_q` returns success but
  fails to create a CSV `# BROKEN`. Do not attempt; always go through
  the ABC flux-linkage data table and convert to dq after parsing.
- Broad loops over report types, solution contexts, expressions, or
  report creation can crash AEDT `# BROKEN` (see Report-Loop Discipline).
- Rebuilding winding groups with `BoundarySetup.EditWindingGroup(...)` with
  the full arg block (`Type/IsSolid/Current/Resistance/Inductance/Voltage/
  ParallelBranchesNum/Phase`) made subsequent `Analyze(...)` fail on
  `Maxwell2DDesign4` `# BROKEN`. See
  `tmp/aedt_jobs/gui_fem_export_smoke_magnetostatic.json` for the failure.
  See "Current Sweeps" below for what to try instead.

## Safe Script Shape

Use this structure for every GUI-run script:

```python
import json
import os
import traceback

PROJECT_ROOT = r"C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp"
OUT_JSON = os.path.join(PROJECT_ROOT, "tmp", "aedt_jobs", "name_of_script_result.json")

PROJECT_NAME = "ipm_1"
DESIGN_NAME = "Maxwell2DDesign4"


def warn(message):
    try:
        AddWarningMessage(message)
    except BaseException:
        print(message)


def normalize(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        return [normalize(item) for item in list(value)]
    except BaseException:
        return str(value)


def call(fn):
    try:
        return {"ok": True, "value": normalize(fn())}
    except BaseException as exc:
        return {
            "ok": False,
            "error": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-8:],
        }


def main():
    project = oDesktop.SetActiveProject(PROJECT_NAME)
    design = project.SetActiveDesign(DESIGN_NAME)
    return {
        "status": "ok",
        "project": PROJECT_NAME,
        "design": DESIGN_NAME,
        "design_type": call(design.GetDesignType),
        "solution_type": call(design.GetSolutionType),
    }


try:
    payload = main()
except BaseException as exc:
    payload = {
        "status": "error",
        "message": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    }

out_parent = os.path.dirname(OUT_JSON)
if not os.path.exists(out_parent):
    os.makedirs(out_parent)
with open(OUT_JSON, "w") as f:
    json.dump(payload, f, indent=2)

warn("Wrote AEDT GUI script result to: " + OUT_JSON)
```

## Report Export Pattern

Prefer exporting known-good ABC flux linkage reports.

```python
# PROVEN: CreateReport + ExportToFile for FluxLinkage(PhaseA/B/C) against
# the Magnetostatic LastAdaptive solution on Maxwell2DDesign4.
REPORT_NAME = "MCP_FluxLinkage_ABC"
REPORT_TYPE = "Magnetostatic"
DISPLAY_TYPE = "Data Table"
SOLUTION_NAME = "Setup_MagProbe : LastAdaptive"
EXPRESSIONS = [
    "FluxLinkage(PhaseA)",
    "FluxLinkage(PhaseB)",
    "FluxLinkage(PhaseC)",
]

report = design.GetModule("ReportSetup")
names = list(report.GetAllReportNames())
if REPORT_NAME in names:
    report.DeleteReports([REPORT_NAME])
report.CreateReport(
    REPORT_NAME,
    REPORT_TYPE,
    DISPLAY_TYPE,
    SOLUTION_NAME,
    [],
    ["fractions:=", ["All"]],
    ["X Component:=", "fractions", "Y Component:=", EXPRESSIONS],
)
report.ExportToFile(REPORT_NAME, csv_path)
```

Apply the File-Existence Rule (above) after `ExportToFile`. AEDT may
return success without writing a file for unsupported expressions.

## Flux CSV Parse (PROVEN shape)

`Read_ReportToFile` writes a row per "fractions" entry. For the ABC
flux linkage report the LAST row is the converged solution row, and
the first column is `fractions=<n>` followed by the three phase flux
linkages in the order the Y Component was specified. Parse with:

```python
# PROVEN: read_flux_csv is what extracted Phi_A/B/C from per-point CSVs
# in tmp/aedt_jobs/*/point_exports/point_NNN_fluxlinkage_abc.csv
def read_flux_csv(path):
    with open(path, "r") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    if len(header) < 4:
        raise RuntimeError("Expected >=4 columns in flux CSV, got: " + str(header))
    if not rows:
        raise RuntimeError("Flux CSV had no data rows: " + path)
    last = rows[-1]
    phi_a = float(last[1])
    phi_b = float(last[2])
    phi_c = float(last[3])
    return {"header": header, "row": last, "PhiA": phi_a, "PhiB": phi_b, "PhiC": phi_c}
```

Never trust the header row alone - confirm `len(header) >= 4` and
`len(rows) >= 1`. Skip CSVs that look empty or incomplete by re-running
the export for that point.

## Finite Checks

Do not use `math.isfinite` (IronPython 2.7 does not expose it). Use
this helper instead:

```python
def is_finite(value):
    try:
        return not (math.isnan(value) or math.isinf(value))
    except BaseException:
        return False
```

## ABC To DQ Conversion

Use this conversion for exported phase flux linkages:

```python
def dq_from_abc(phi_a, phi_b, phi_c, theta_re):
    phi_d = (2.0 / 3.0) * (
        phi_a * math.cos(theta_re)
        + phi_b * math.cos(theta_re - 2 * math.pi / 3)
        + phi_c * math.cos(theta_re + 2 * math.pi / 3)
    )
    phi_q = (2.0 / 3.0) * (
        -phi_a * math.sin(theta_re)
        - phi_b * math.sin(theta_re - 2 * math.pi / 3)
        - phi_c * math.sin(theta_re + 2 * math.pi / 3)
    )
    return phi_d, phi_q


def abc_from_dq(id_value, iq_value, theta_re):
    ia = math.cos(theta_re) * id_value - math.sin(theta_re) * iq_value
    ib = math.cos(theta_re - 2 * math.pi / 3) * id_value - math.sin(theta_re - 2 * math.pi / 3) * iq_value
    ic = -(ia + ib)
    return ia, ib, ic
```

Final FEM training CSV contract:

```text
Id,Iq,Phi_d,Phi_q
```

Only write the final CSV after all required rows are present and finite.

## Current Sweeps

The biggest unresolved question in this project is: how do we sweep
phase current across Id/Iq points without breaking `Analyze` on
Student AEDT's `Maxwell2DDesign4`?

`# BROKEN`: `BoundarySetup.EditWindingGroup(...)` with the full arg
block (`Type/IsSolid/Current/Resistance/Inductance/Voltage/
ParallelBranchesNum/Phase`) made subsequent `Analyze("Setup_MagProbe")`
fail at the very first sweep point. Confirmed in
`tmp/aedt_jobs/gui_fem_export_smoke_magnetostatic.json`.

For sweep scripts, prefer these paths in priority order:

1. Export already-solved variations without modifying excitations. Best
   if a parametric setup has already produced a family of solved points.
2. Change existing local variables if the design exposes `Id`, `Iq`,
   `Ia`, `Ib`, or `Ic` as local variables. This was PROVEN on
   `Maxwell2DDesign1` via
   `tmp/aedt_projects/ipm_1_probe/scriptenv_fem_export_unit_export.py`:

   ```python
   # PROVEN on Maxwell2DDesign1 (transient sibling). NOT yet verified
   # on the Magnetostatic Maxwell2DDesign4. Probe first.
   design.ChangeProperty([
       "NAME:AllTabs",
       [
           "NAME:LocalVariableTab",
           ["NAME:PropServers", "LocalVariables"],
           ["NAME:ChangedProps",
               ["NAME:Ia", "Value:=", "%.9gA" % ia],
               ["NAME:Ib", "Value:=", "%.9gA" % ib],
               ["NAME:Ic", "Value:=", "%.9gA" % ic],
           ],
       ],
   ])
   ```

3. Narrow `ChangeProperty` against `BoundarySetup` for ONE property
   at a time (`Current` only). NOT yet verified on
   `Maxwell2DDesign4`; an attempted `GetProperties("BoundarySetup",
   "BoundarySetup:PhaseA")` returned "call failed" in
   `gui_diagnose_magnetostatic_after_failed_sweep.json`. The correct
   prop-server name is unknown until a recording is made. Try the
   following candidates in order, but never all in one script - the
   skill user runs probe separately, picks the hit, and uses only
   that one in the export script:
   - `BoundarySetup:PhaseA`
   - `PhaseA` (no prefix)
   - `Excitation:PhaseA`
   - `Excitation`

4. If none of the above can be verified, fall back to a diagnostic
   script that captures `ValidateDesign()`, message-manager output,
   and current report exports BEFORE attempting another solve. Do NOT
   keep trying edits at 03:00 on the overnight run - emit status and
   stop.

### Pending recorded sequence

A GUI-recorded `Tools -> Record Script` session in the Automate tab
that changes PhaseA/B/C winding current values (without using the full
`EditWindingGroup` arg block) and then `Analyze`s the design is the
cleanest path forward. Once the user pastes that recorded sequence,
append it to this skill as "Current-change recorded sequence" and
delete the "Pending" header here. Until that happens, any current-
sweep export script MUST include a smoke stage (2x2) and ABORT the
full run if the smoke stage fails, instead of grinding all 1600
points on a broken edit path.

## Sweep Failure Capture (Hard)

Never hide an `Analyze(...)` failure. Include each of these in the
result JSON for the failing point so the user can diagnose without
reproducing:

- point index
- requested `Id/Iq`
- phase currents applied
- `ValidateDesign()`
- `oDesktop.GetMessages(project, design, level)` for levels `0..3`
  captured IMMEDIATELY after the failed `Analyze`, not after any
  subsequent API call (later calls clear the most recent error string).
- any global level-2 errors: `oDesktop.GetMessages("", "", 2)`.
- the chosen current-change method name, so it is obvious which path
  was being tried.

If an `Analyze` failure occurs at point N during a long sweep, write
the failing point's full diagnostics to
`tmp/aedt_jobs/<job_id>/point_NNN_failure.json`, then abort the
sweep. Do NOT attempt to continue past a failure on an overnight run -
the next point will likely fail too and you will corrupt progress.

## Resume Discipline

For any sweep script that may run longer than one session, set
`RESUME = True` and use a `progress.csv` keyed by `(Id, Iq)`.
At the start of `main()`, read `progress.csv` if it exists, build
the set of already-completed keys, and skip grids whose key is
present. This lets the user close AEDT, restart, and resume the
sweep from the same script without losing progress.

## What To Tell The User

For every generated script, give the user:

1. The absolute script path to run in AEDT (`Automation -> Run Script`).
2. The exact `Get-Content` command for the result JSON.
3. The exact `Get-Content` or `Get-ChildItem` command for produced CSVs.
4. A brief statement of whether the script mutates the design, solves,
   creates reports, exports reports, or only diagnoses.
5. For sweep scripts, the smoke stage the script runs before the full
   sweep, and the exact `Get-Content` path of the smoke-stage result
   JSON, so the user can opt to interrupt after smoke rather than wait
   for 1600 points to fail blindly.