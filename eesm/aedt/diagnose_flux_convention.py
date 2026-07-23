"""Determine the correct flux-extraction convention from evidence.

Runs against a DISPOSABLE COPY of the working RMxprt-derived project.
Driven headless by eesm/aedt/run_flux_convention_diagnostic.ps1, which uses
the same ansysedtsv.exe -ng -RunScriptAndExit pattern as the existing r9
diagnostics. It can also be run from the GUI via Automation -> Run Script,
in which case it falls back to the active project.

Why this script exists
----------------------
The Task 9 campaign exported per-phase flux linkages whose zero-sequence
component averaged 40% of the dq magnitude. Offline analysis proved the
imbalance cannot be removed by any phase permutation, sign flip, or Park
angle: the best achievable zero-sequence over all 48 relabelings is still
0.343 (current export: 0.404), where a correct winding gives < 0.01.

That rules out a post-processing bug and localises the fault upstream, in
what AEDT reports for the winding in this fractions=4 sector model. It does
NOT tell us which upstream mechanism is responsible. This script gathers
the evidence needed to decide, without guessing.

It writes raw numbers and makes no correction of its own. Nothing here
authorises a campaign, qualification, or training run.

What it collects
----------------
1. Model inventory: coil -> winding -> polarity -> conductor count, the
   symmetry multiplier, and the model depth, read back from the live model
   rather than assumed from the build script.
2. For each probe point, three independent flux measurements:
   a. winding-level FluxLinkage(PhaseX)          <- what the campaign used
   b. per-coil FluxLinkage(<coil>)               <- probed; may not exist
   c. surface integral of A_z over each coil     <- gauge-sensitive but
                                                    differencable, and
                                                    always available
3. Torque, mesh, and convergence evidence per point.

Interpreting the output is described in
eesm/docs/FLUX_EXTRACTION_FIX.md.
"""

import json
import math
import os
import time
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))

DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"
SOLUTION_NAME = "Setup_Qual : LastAdaptive"
PHASES = ("PhaseA", "PhaseB", "PhaseC")
FIELD_WINDING = "Field"

OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "flux_convention_diagnostic")
OUT_JSON = os.path.join(OUT_DIR, "flux_convention_evidence.json")

#: Disposable copy created by the PowerShell runner. When running headless
#: the script opens this explicitly; when run from the GUI with no such file
#: present it falls back to whatever project is active.
PROJECT_NAME = "eesm_fluxdiag_01"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)

#: Probe points. Deliberately tiny and physically decisive.
#:
#:   field_only  - only the rotor field is energised, so lambda_abc is a
#:                 direct measurement of the rotor field axis. If the abc
#:                 set is balanced, the d-axis electrical angle falls
#:                 straight out of it with no rotor rotation required.
#:   d_probe     - stator d-axis current alone -> Ld
#:   q_probe     - stator q-axis current alone -> Lq
#:   combined    - a normal operating point for cross-checking
#:
#: The all-zero "source-free origin" is deliberately EXCLUDED: the
#: qualification notes record that AEDT Student reproducibly exits inside
#: Analyze() for that redundant solve. Set PROBE_SOURCE_FREE_ORIGIN = True
#: only if you want to retest that, and expect a crash.
PROBE_SOURCE_FREE_ORIGIN = False

PROBE_POINTS = [
    ("field_only", 0.0, 0.0, 2.0),
    ("d_probe_negative", -50.0, 0.0, 0.0),
    ("q_probe_positive", 0.0, 50.0, 0.0),
    ("combined", -40.0, 60.0, 4.0),
]
if PROBE_SOURCE_FREE_ORIGIN:
    PROBE_POINTS.insert(0, ("source_free_origin", 0.0, 0.0, 0.0))

#: Rotor position used by the existing exporter. Recorded, not trusted.
LEGACY_ROTOR_POSITION_DEG = 180.0


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def attempt(label, thunk):
    """Run thunk, capturing success/failure without aborting the probe."""
    try:
        return {"label": label, "ok": True, "value": thunk()}
    except BaseException as exc:
        return {
            "label": label,
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc().splitlines()[-4:],
        }


def as_text_list(values):
    try:
        return [str(v) for v in list(values)]
    except BaseException:
        return []


# ---------------------------------------------------------------------------
# Model inventory
# ---------------------------------------------------------------------------

def collect_inventory(design, editor):
    """Read the winding/coil topology back from the live model."""
    inventory = {}
    boundary = design.GetModule("BoundarySetup")

    inventory["boundaries"] = attempt(
        "BoundarySetup.GetBoundaries",
        lambda: as_text_list(boundary.GetBoundaries()),
    )
    inventory["sheets"] = attempt(
        "GetObjectsInGroup(Sheets)",
        lambda: as_text_list(editor.GetObjectsInGroup("Sheets")),
    )
    inventory["excitations"] = attempt(
        "GetExcitations",
        lambda: as_text_list(boundary.GetExcitations()),
    )
    inventory["model_depth"] = attempt(
        "Design Settings ModelDepth",
        lambda: str(design.GetDesignSettings()),
    )
    inventory["symmetry_multiplier"] = attempt(
        "ModelSetup symmetry multiplier",
        lambda: str(design.GetModule("ModelSetup").GetSymmetryMultiplier()),
    )

    # Per-coil assignment. The property path differs across AEDT versions,
    # so try the documented routes and record which one worked.
    coil_details = []
    names = inventory["boundaries"].get("value") or []
    for name in names:
        entry = {"boundary": name}
        entry["assignment"] = attempt(
            "GetBoundaryAssignment(%s)" % name,
            lambda n=name: as_text_list(boundary.GetBoundaryAssignment(n)),
        )
        for prop in ("Winding", "PolarityType", "Conductor number", "Type"):
            entry[prop] = attempt(
                "GetPropertyValue(%s.%s)" % (name, prop),
                lambda n=name, p=prop: str(
                    design.GetPropertyValue("BoundarySetupTab", n, p)
                ),
            )
        coil_details.append(entry)
    inventory["coil_details"] = coil_details
    return inventory


# ---------------------------------------------------------------------------
# Flux measurements
# ---------------------------------------------------------------------------

def read_report_expressions(design, report_name, expressions, csv_path):
    """Create a data table for the given expressions and read it back."""
    report = design.GetModule("ReportSetup")
    existing = as_text_list(report.GetAllReportNames())
    if report_name in existing:
        report.DeleteReports([report_name])
    report.CreateReport(
        report_name, "Magnetostatic", "Data Table", SOLUTION_NAME, [],
        ["fractions:=", ["All"]],
        ["X Component:=", "fractions", "Y Component:=", list(expressions)],
    )
    report.ExportToFile(report_name, csv_path)
    report.DeleteReports([report_name])
    if not (os.path.exists(csv_path) and os.path.getsize(csv_path) > 0):
        raise RuntimeError("export produced no file: " + csv_path)
    stream = open(csv_path, "r")
    try:
        lines = [line.strip() for line in stream.readlines() if line.strip()]
    finally:
        stream.close()
    if len(lines) < 2:
        raise RuntimeError("export had no data row: " + csv_path)
    header = [h.strip().strip('"') for h in lines[0].split(",")]
    values = [v.strip().strip('"') for v in lines[1].split(",")]
    out = {}
    for key, value in zip(header, values):
        try:
            out[key] = float(value)
        except ValueError:
            out[key] = value
    return out


def integrate_az_over_sheet(design, sheet_name):
    """Gauge-sensitive but differencable: integral of A_z over one sheet.

    Flux linkage computed as (N/Area)*depth*(integral over the go side
    minus integral over the return side) is independent of the vector
    potential gauge constant, because the constant cancels in the
    difference. Winding-level FluxLinkage does not necessarily perform
    that differencing when both sides of a full-pitch coil carry the same
    assigned polarity, which is the case in this sector model.
    """
    fields = design.GetModule("FieldsReporter")
    fields.CalcStack("clear")
    fields.EnterQty("A")
    fields.CalcOp("ScalarZ")
    fields.EnterSurf(sheet_name)
    fields.CalcOp("Integrate")
    value = fields.GetTopEntryValue(SOLUTION_NAME, [])
    fields.CalcStack("clear")
    return float(str(list(value)[0]))


def sheet_area(design, sheet_name):
    fields = design.GetModule("FieldsReporter")
    fields.CalcStack("clear")
    fields.EnterScalar(1.0)
    fields.EnterSurf(sheet_name)
    fields.CalcOp("Integrate")
    value = fields.GetTopEntryValue(SOLUTION_NAME, [])
    fields.CalcStack("clear")
    return float(str(list(value)[0]))


# ---------------------------------------------------------------------------
# Point solve
# ---------------------------------------------------------------------------

def apply_currents(design, id_a, iq_a, if_a, theta_e_deg):
    theta = theta_e_deg * math.pi / 180.0
    phase_values = [
        id_a * math.cos(angle) - iq_a * math.sin(angle)
        for angle in (theta, theta - 2 * math.pi / 3, theta + 2 * math.pi / 3)
    ]
    boundary = design.GetModule("BoundarySetup")
    for phase, value in zip(PHASES, phase_values):
        boundary.EditWindingGroup(phase, [
            "NAME:" + phase, "Type:=", "Current",
            "Current:=", "%.12gA" % value,
        ])
    boundary.EditWindingGroup(FIELD_WINDING, [
        "NAME:" + FIELD_WINDING, "Type:=", "Current",
        "Current:=", "%.12gA" % if_a,
    ])
    return {
        "theta_e_deg": theta_e_deg,
        "phase_currents_a": phase_values,
        "field_current_a": if_a,
    }


def probe_point(design, name, id_a, iq_a, if_a, sheets):
    record = {
        "point": name,
        "id_a": id_a,
        "iq_a": iq_a,
        "if_a": if_a,
    }
    record["applied"] = apply_currents(
        design, id_a, iq_a, if_a, LEGACY_ROTOR_POSITION_DEG
    )

    started = time.time()
    record["solve"] = attempt(
        "Analyze(%s)" % SETUP_NAME, lambda: design.Analyze(SETUP_NAME)
    )
    record["solve_seconds"] = time.time() - started
    if not record["solve"]["ok"]:
        return record

    csv_dir = os.path.join(OUT_DIR, "raw", name)
    ensure_dir(csv_dir)

    # (a) winding-level flux linkage - the method the campaign used
    record["winding_flux_linkage"] = attempt(
        "FluxLinkage(PhaseX)",
        lambda: read_report_expressions(
            design,
            "DIAG_Winding_Flux",
            ["FluxLinkage(%s)" % p for p in PHASES]
            + ["FluxLinkage(%s)" % FIELD_WINDING],
            os.path.join(csv_dir, "winding_flux.csv"),
        ),
    )

    # (b) per-coil flux linkage - probed; the expression may not be valid
    coil_sheets = [s for s in sheets if s.startswith("Coil")]
    if coil_sheets:
        record["coil_flux_linkage"] = attempt(
            "FluxLinkage(<coil boundary>)",
            lambda: read_report_expressions(
                design,
                "DIAG_Coil_Flux",
                ["FluxLinkage(%s)" % c for c in coil_sheets],
                os.path.join(csv_dir, "coil_flux.csv"),
            ),
        )

    # (c) A_z surface integral per sheet - always available, gauge-sensitive
    az = {}
    area = {}
    for sheet in sheets:
        az[sheet] = attempt(
            "integrate A_z over %s" % sheet,
            lambda s=sheet: integrate_az_over_sheet(design, s),
        )
        area[sheet] = attempt(
            "area of %s" % sheet, lambda s=sheet: sheet_area(design, s)
        )
    record["az_integral_wb_m"] = az
    record["sheet_area_m2"] = area

    record["torque"] = attempt(
        "Torque_FEM output variable",
        lambda: str(
            design.GetModule("OutputVariable").GetOutputVariableValue(
                "Torque_FEM", "", SOLUTION_NAME, "Magnetostatic", []
            )
        ),
    )
    return record


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ensure_dir(OUT_DIR)
    payload = {
        "artifact_type": "flux_convention_diagnostic",
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "design": DESIGN_NAME,
        "setup": SETUP_NAME,
        "legacy_rotor_position_deg": LEGACY_ROTOR_POSITION_DEG,
        "campaign_binding_authorized": False,
        "qualification_authorized": False,
        "training_authorized": False,
        "notes": [
            "Run against a DISPOSABLE COPY. This script solves and mutates "
            "winding currents.",
            "No correction is applied here. This collects evidence only.",
        ],
    }

    try:
        if os.path.isfile(PROJECT_PATH):
            project = oDesktop.OpenProject(PROJECT_PATH)
            payload["project_source"] = "disposable_copy"
            payload["project_path"] = PROJECT_PATH
        else:
            project = oDesktop.GetActiveProject()
            payload["project_source"] = "active_project_fallback"
        if project is None:
            raise RuntimeError(
                "No project available. Either run "
                "run_flux_convention_diagnostic.ps1 (which creates the "
                "disposable copy at %s), or open a disposable copy in the "
                "GUI before running." % PROJECT_PATH
            )
        payload["project"] = str(project.GetName())
        design = project.SetActiveDesign(DESIGN_NAME)
        if design is None:
            raise RuntimeError("Design %s not found" % DESIGN_NAME)
        editor = design.SetActiveEditor("3D Modeler")

        payload["inventory"] = collect_inventory(design, editor)
        sheets = payload["inventory"]["sheets"].get("value") or []
        payload["sheets_probed"] = sheets

        results = []
        for name, id_a, iq_a, if_a in PROBE_POINTS:
            results.append(probe_point(design, name, id_a, iq_a, if_a, sheets))
        payload["points"] = results
        payload["status"] = "collected"
    except BaseException as exc:
        payload["status"] = "error"
        payload["error"] = str(exc)
        payload["traceback"] = traceback.format_exc().splitlines()
    finally:
        stream = open(OUT_JSON, "w")
        try:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.flush()
        finally:
            stream.close()
    return payload


if __name__ == "__main__":
    main()
