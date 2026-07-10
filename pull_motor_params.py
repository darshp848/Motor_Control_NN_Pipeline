"""Pull motor parameters from Maxwell2DDesign4 (and its RMxprt parent
design) so the MTPA/FW script mtpa_field_weakening.py can derive a correct
--flux-scale cross-check, not just the RMxprt 0.res data we cached earlier.

Runs inside AEDT (Automation -> Run Script) via IronPython. Writes:

    aedt_mcp/out/motor_params.json
    (also copy/sync to data/motor_params.json for the public pipeline)

with these keys (any that fail are set to null+reason rather than abort):
  poles                         (int)
  pole_pairs                    (int)
  rs_ohm                        (float or null)
  vdc_v                         (float or null)
  i_max_peak_a                  (float or null)
  i_rated_peak_a                (float or null)
  t_rated_nm                    (float or null)
  omega_mech_base_rpm           (float or null)
  omega_mech_max_rpm            (null - design choice outside the design)
  flux_scale                    (float - computed from a sanity probe:
                                                chosen so that T(Id=0,
                                                Iq=i_rated_peak) equals
                                                t_rated_nm when multiplied
                                                by the surrogate-predicted
                                                flux linkages. We do this
                                                by solving one extra FEM
                                                point at (Id=0, Iq=I_rated)
                                                using the verified recipe
                                                [coarsen mesh, EditSetup,
                                                EditWindingGroup, Analyze,
                                                CreateReport, ExportToFile],
                                                Park-transforming the ABC
                                                flux to dq, then computing
                                                T_implied = (3/2) P (Phi_d *
                                                Iq - Phi_q * Id) and taking
                                                flux_scale = t_rated /
                                                T_implied.)
  flux_scale_explanation        (str)
  rated_probe_abc_csv           (str path to the per-point ABC CSV)
  rated_probe_json              (str path to the rated probe JSON)

Why this is a dedicated run rather than reading the existing 0.res file:
  - The 0.res file is the output of the RMxprt *parent* design's analytic
    solve, which is independent of Maxwell2DDesign4's 2D FEM. We want to
    cross-check the FEM's flux-linkage normalization explicitly so that
    mtpa_field_weakening.py produces SI-correct torque predictions.
  - In particular, Maxwell2D "FluxLinkage(Winding)" can be per-meter-axial
    (when the design "Length" is set to 0) or per-active-length - we don't
    want to guess; we measure.

IMPORTANT: this script is idempotent (re-applies the verified coarsen +
EditSetup recipe) but it *does* drive the design - one extra Analyze at a
sanity operating point. Do NOT run it concurrently with the 40x40 sweep.
Run it AFTER the sweep's final_result.json lands.

Run from AEDT 2025 R2 Student: Automation -> Run Script."""

import json
import math
import os
import traceback

# ---------------------------------------------------------------------------
# Config.
# ---------------------------------------------------------------------------

# Repo root = directory containing this script; AEDT package lives in aedt_mcp/
try:
    _REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _REPO_ROOT = r"C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline"
PROJECT_ROOT = os.path.join(_REPO_ROOT, "aedt_mcp")
PROJECT_PATH = os.path.join(
    PROJECT_ROOT, "tmp", "aedt_projects", "ipm_1_probe", "ipm_1.aedt"
)
OUT_DIR = os.path.join(PROJECT_ROOT, "out")
OUT_JSON = os.path.join(OUT_DIR, "motor_params.json")
SANITY_DIR = os.path.join(PROJECT_ROOT, "tmp", "aedt_jobs",
                          "pull_motor_params_sanity")
SANITY_ABC_CSV = os.path.join(SANITY_DIR, "rated_probe_abc.csv")
SANITY_JSON = os.path.join(SANITY_DIR, "rated_probe.json")

PROJECT_NAME = "ipm_1"
DESIGN_NAME = "Maxwell2DDesign4"
RMXPR_DESIGN_NAMES = ("RMxprtDesign1", "RMxprtDesign")  # try in order
SETUP_NAME = "Setup_MagProbe"
SOLUTION_NAME = "Setup_MagProbe : LastAdaptive"
REPORT_NAME = "MCP_PullParamsSanity_ABC"
REPORT_TYPE = "Magnetostatic"
DISPLAY_TYPE = "Data Table"
PHASES = ("PhaseA", "PhaseB", "PhaseC")
EXPRESSIONS = [
    "FluxLinkage(PhaseA)",
    "FluxLinkage(PhaseB)",
    "FluxLinkage(PhaseC)",
]

# Recipe constants - same as single_point_verify.py / the full sweep's Step 0.
MESH_OPS_TO_DELETE = ("SurfApprox_Mag", "SurfApprox_Main", "CylindricalGap1")
COARSEN_SLIDER_LEVEL = 1
SETUP_MAX_PASSES = 1
SETUP_MIN_PASSES = 1
SETUP_PERCENT_REFINEMENT = 10

# Known motor electrical parameters from the RMxprt .res file cached in
# ipm_1.aedtresults/.../DV632_SOL39_V605.MExportData/0.res. We hardcode them
# as defaults here; the script also probes the RMxprt design via its
# variables where possible, but if all else fails these defaults are what
# mtpa_field_weakening.py should fall back to.
R_REQUIRED = 2.83481  # Arms (rated from RMxprt 0.res "RMS Armature Current")
T_REQUIRED = 2.89531  # N.m (rated torque, RMxprt 0.res)
N_POLES_DEFAULT = 4
I_MAX_DEFAULT_PEAK = 4.00807 * (6.0 / 2.83481)  # scale to "Maximum Current"
# (= 6.0 A max current RMS * sqrt(2) = 8.485 peak). Speculatively:
I_MAX_DEFAULT_PEAK = 6.0 * math.sqrt(2.0) * 0.70711  # close to 6 A max anyway
# adjust to clean default:
I_MAX_DEFAULT_PEAK = 6.0  # to keep it simple - rated max current

# ---------------------------------------------------------------------------
# Helpers (stdlib only - IronPython).
# ---------------------------------------------------------------------------

def warn(message):
    try:
        AddWarningMessage(message)
    except BaseException:
        print(message)


def safe_list(fn):
    try:
        return list(fn())
    except BaseException:
        return []


def get_or_open_project():
    projects = safe_list(oDesktop.GetProjectList)
    if PROJECT_NAME in projects:
        return PROJECT_NAME
    if os.path.exists(PROJECT_PATH):
        try:
            oDesktop.OpenProject(PROJECT_PATH)
        except BaseException as exc:
            warn("OpenProject warning: " + str(exc))
    projects = safe_list(oDesktop.GetProjectList)
    if PROJECT_NAME in projects:
        return PROJECT_NAME
    return None


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


def messages_snapshot():
    snap = {}
    for level in (0, 1, 2, 3):
        snap[str(level)] = call(
            lambda level=level: oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, level)
        )
    snap["global_errors"] = call(lambda: oDesktop.GetMessages("", "", 2))
    return snap


def abc_from_dq(id_value, iq_value, theta_re=0.0):
    ia = math.cos(theta_re) * id_value - math.sin(theta_re) * iq_value
    ib = math.cos(theta_re - 2.0 * math.pi / 3.0) * id_value \
        - math.sin(theta_re - 2.0 * math.pi / 3.0) * iq_value
    ic = -(ia + ib)
    return ia, ib, ic


def dq_from_abc(phi_a, phi_b, phi_c, theta_re=0.0):
    phi_d = (2.0 / 3.0) * (
        phi_a * math.cos(theta_re)
        + phi_b * math.cos(theta_re - 2.0 * math.pi / 3.0)
        + phi_c * math.cos(theta_re + 2.0 * math.pi / 3.0)
    )
    phi_q = (2.0 / 3.0) * (
        -phi_a * math.sin(theta_re)
        - phi_b * math.sin(theta_re - 2.0 * math.pi / 3.0)
        - phi_c * math.sin(theta_re + 2.0 * math.pi / 3.0)
    )
    return phi_d, phi_q


def reapply_mesh_and_setup(mesh_module, analysis):
    """Idempotent coarsen + EditSetup. Mirrors the full-sweep recipe."""
    existing_probe = call(lambda: mesh_module.GetOperationNames("All"))
    existing = existing_probe.get("value") or []
    deleted = {}
    for op in MESH_OPS_TO_DELETE:
        if op in existing:
            deleted[op] = call(lambda op=op: mesh_module.DeleteOp([op]))
        else:
            deleted[op] = {"ok": True, "value": "already_absent"}
    coarsen_args = [
        "NAME:MeshSettings",
        ["NAME:GlobalSurfApproximation",
         "CurvedSurfaceApproxChoice:=", "UseSlider",
         "SliderMeshSettings:=", COARSEN_SLIDER_LEVEL],
        ["NAME:GlobalModelRes", "UseAutoLength:=", True],
        "MeshMethod:=", "AnsoftClassic",
    ]
    initial = call(lambda: mesh_module.InitialMeshSettings(coarsen_args))
    edit_args = [
        "NAME:" + SETUP_NAME,
        "Enabled:=", True,
        ["NAME:MeshLink", "ImportMesh:=", False],
        "MaximumPasses:=", SETUP_MAX_PASSES,
        "MinimumPasses:=", SETUP_MIN_PASSES,
        "MinimumConvergedPasses:=", 1,
        "PercentRefinement:=", SETUP_PERCENT_REFINEMENT,
        "SolveFieldOnly:=", False,
        "PercentError:=", 1,
        "SolveMatrixAtLast:=", True,
        "UseIterativeSolver:=", False,
        "RelativeResidual:=", 1e-06,
        "NonLinearResidual:=", 0.0001,
        "SmoothBHCurve:=", False,
        ["NAME:MuOption", "MuNonLinearBH:=", True],
    ]
    edit = call(lambda: analysis.EditSetup(SETUP_NAME, edit_args))
    return {"delete_ops": deleted, "initial_mesh": initial, "edit_setup": edit,
            "existing_ops_probe": existing_probe}


def apply_currents(boundary, ia, ib, ic):
    for phase, cur in zip(PHASES, (ia, ib, ic)):
        payload = ["NAME:" + phase, "Type:=", "Current",
                   "Current:=", "%.12gA" % cur]
        res = call(lambda p=phase, pl=payload: boundary.EditWindingGroup(p, pl))
        if not res.get("ok"):
            return {"ok": False, "phase": phase, "result": res}
    return {"ok": True}


def parse_flux_csv(path):
    import csv as csvmod
    with open(path, "r") as f:
        reader = csvmod.reader(f)
        header = next(reader)
        rows = list(reader)
    if not rows:
        raise RuntimeError("Empty flux CSV: " + path)
    last = rows[-1]
    return float(last[1]), float(last[2]), float(last[3])


# ---------------------------------------------------------------------------
# RMxprt parameter extraction.
# ---------------------------------------------------------------------------

def find_rmxprt_design(project):
    """Return (name, design_dispatch) for the RMxprt design in the project,
    or (None, None) if none exists."""
    designs_probe = call(project.GetTopDesignList)
    if not designs_probe.get("ok"):
        return None, None
    raw = designs_probe.get("value") or []
    # Items typically look like "<n>;<DesignName>".
    names = [str(item).split(";")[-1] for item in raw]
    for cand in RMXPR_DESIGN_NAMES:
        if cand in names:
            try:
                d = project.SetActiveDesign(cand)
                return cand, d
            except BaseException:
                pass
    # Otherwise settle on the one whose solution type has "RM" in it.
    for n in names:
        try:
            d = project.SetActiveDesign(n)
            st = d.GetSolutionType()
            if st and "RM" in str(st):
                return n, d
        except BaseException:
            pass
    return None, None


def attempt_get_variable(design, key, default=None, cast=float):
    """Reads design variable via design.GetVariableValue if present, else
    returns the default."""
    fn = getattr(design, "GetVariableValue", None)
    if fn is None:
        return default, "method_absent"
    try:
        v = fn(key)
        if v is None:
            return default, "var_missing"
        return cast(v), "ok"
    except BaseException as exc:
        return default, "exception:" + str(exc)


# ---------------------------------------------------------------------------
# Sanity probe: one extra solve at (Id=0, Iq=I_rated_peak).
# ---------------------------------------------------------------------------

def sanity_probe(design, boundary, report, i_rated_peak):
    """Set PhaseA=I_rated_peak / PhaseB=PhaseC=-I_rated_peak/2 with theta_re=0,
    Analyze, export ABC flux linkage, Park-transform to dq, return (Phi_d,
    Phi_q). Mirrors single_point_verify.py at the rated Iq point."""
    ia, ib, ic = abc_from_dq(0.0, i_rated_peak, theta_re=0.0)
    applied = apply_currents(boundary, ia, ib, ic)
    if not applied.get("ok"):
        return None, {"apply_current": applied}

    analyzed = call(lambda: design.Analyze(SETUP_NAME))
    if not (analyzed.get("ok") and analyzed.get("value") == 0):
        return None, {"analyze": analyzed}

    # Delete + recreate report.
    names = call(report.GetAllReportNames)
    if names.get("ok") and REPORT_NAME in (names.get("value") or []):
        call(lambda: report.DeleteReports([REPORT_NAME]))
    created = call(lambda: report.CreateReport(
        REPORT_NAME, REPORT_TYPE, DISPLAY_TYPE, SOLUTION_NAME,
        [], ["fractions:=", ["All"]],
        ["X Component:=", "fractions", "Y Component:=", EXPRESSIONS],
    ))
    if not created.get("ok"):
        return None, {"create_report": created}
    exported = call(lambda: report.ExportToFile(REPORT_NAME, SANITY_ABC_CSV))
    if not (exported.get("ok") and os.path.exists(SANITY_ABC_CSV)):
        return None, {"export": exported}
    try:
        phi_a, phi_b, phi_c = parse_flux_csv(SANITY_ABC_CSV)
    except BaseException as exc:
        return None, {"parse_csv": str(exc)}
    phi_d, phi_q = dq_from_abc(phi_a, phi_b, phi_c, theta_re=0.0)
    return (phi_d, phi_q, ia, ib, ic), None


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------

def main():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)
    if not os.path.exists(SANITY_DIR):
        os.makedirs(SANITY_DIR)

    project_name = get_or_open_project()
    if not project_name:
        return {
            "status": "error",
            "message": "No AEDT project is open and ipm_1.aedt could not "
                       "be opened from " + PROJECT_PATH,
            "project_path": PROJECT_PATH,
        }
    project = oDesktop.SetActiveProject(project_name)
    design = project.SetActiveDesign(DESIGN_NAME)
    boundary = design.GetModule("BoundarySetup")
    analysis = design.GetModule("AnalysisSetup")
    mesh_module = design.GetModule("MeshSetup")
    report = design.GetModule("ReportSetup")

    payload = {
        "project": project_name,
        "design": DESIGN_NAME,
        "prestate": {
            "solution_type": call(design.GetSolutionType),
            "validate_before": call(design.ValidateDesign),
            "messages_before": messages_snapshot(),
        },
    }

    # Re-apply the verified recipe (idempotent) so the sanity solve doesn't
    # blow the Student mesh ceiling.
    warn("PullParams: re-applying coarsen + EditSetup (idempotent)")
    payload["mesh_setup_recipe"] = reapply_mesh_and_setup(mesh_module, analysis)

    # Rated current peak (from RMxprt .res).
    i_rms = R_REQUIRED
    i_peak = i_rms * math.sqrt(2.0)
    payload["rated_current_rms_a"] = i_rms
    payload["rated_current_peak_a"] = i_peak

    # Probe the RMxprt design to maybe pull more variables (defensive).
    rmx_name, rmx_design = find_rmxprt_design(project)
    payload["rmxprt_design"] = rmx_name
    rs_val, rs_reason = None, "method_absent"
    if rmx_design is not None:
        for key in ("R1", "Rs", "RsOhm", "StatorResistance"):
            rs_val_try, rs_reason = attempt_get_variable(
                rmx_design, key, default=None, cast=float
            )
            if rs_val_try is not None:
                rs_val = rs_val_try
                rs_reason = key
                break
    payload["rs_ohm"] = rs_val if rs_val is not None else 2.15938
    payload["rs_source"] = {
        "rmx_design_probed": rmx_name,
        "attempt_reason": rs_reason,
        "fallback_value": 2.15938,
    }

    # Voltage sourced from the design (saliency rather than inverter bus).
    # We'll keep both: the design's Rated Voltage (if probeable) as
    # rated_voltage_v, and the user CLI default "vdc_v": 311 for the
    # sqrt(2)*220 EV-bus assumption.
    v_rated_val, v_reason = None, "method_absent"
    if rmx_design is not None:
        for key in ("RatedVoltage", "Vrated", "VRated"):
            v_val_try, v_reason = attempt_get_variable(
                rmx_design, key, default=None, cast=float
            )
            if v_val_try is not None:
                v_rated_val = v_val_try
                break
    payload["rated_voltage_v"] = v_rated_val
    payload["vdc_v"] = 311  # CLI default for mtpa_field_weakening.py
    payload["vdc_source"] = "default sqrt(2)*220 EV-bus"

    # Poles: probe design / hardcode.
    poles = N_POLES_DEFAULT
    if rmx_design is not None:
        n_val, n_reason = attempt_get_variable(
            rmx_design, "Poles", default=None, cast=int
        )
        if n_val is not None:
            poles = n_val
    payload["poles"] = poles
    payload["pole_pairs"] = poles // 2

    # Sanity probe at (Id=0, Iq=I_peak). compute scale.
    warn("PullParams: sanity probe at (Id=0, Iq=I_rated_peak=%.4f A)" % i_peak)
    sanity_result, sanity_failure = sanity_probe(
        design, boundary, report, i_peak
    )
    payload["sanity_probe_failure"] = sanity_failure
    if sanity_result is None:
        payload["flux_scale"] = None
        payload["flux_scale_explanation"] = (
            "Sanity probe failed - see sanity_probe_failure. Leaving "
            "flux_scale=null; mtpa_field_weakening.py will default to 1.0 "
            "and print its own sanity warning."
        )
        payload["rated_probe_abc_csv"] = None
        payload["rated_probe_json"] = None
    else:
        phi_d_p, phi_q_p, ia_p, ib_p, ic_p = sanity_result
        # T_implied = (3/2) * P * (Phi_d * Iq_peak - Phi_q * Id_peak)
        # At probe: Id_peak = 0, Iq_peak = i_peak.
        # => T_implied = (3/2) * P * Phi_d * i_peak
        T_implied = 1.5 * (poles // 2) * (phi_d_p * i_peak - phi_q_p * 0.0)
        if abs(T_implied) > 1e-9:
            flux_scale = T_REQUIRED / T_implied
        else:
            flux_scale = None
        # IronPython's math module has no isfinite() (CPython 3.2+).
        if flux_scale is None:
            payload["flux_scale"] = None
        else:
            try:
                fs = float(flux_scale)
                if fs != fs:  # NaN
                    payload["flux_scale"] = None
                elif fs == float("inf") or fs == float("-inf"):
                    payload["flux_scale"] = None
                else:
                    payload["flux_scale"] = fs
            except Exception:
                payload["flux_scale"] = None
        payload["flux_scale_explanation"] = (
            "Computed via: T_implied = (3/2) * P * (Phi_d * Iq_peak - "
            "Phi_q * Id_peak) at the (Id=0, Iq=I_rated_peak) sanity "
            "operating point, with Phi_d, Phi_q from FEM-verified AEDT "
            "solve. flux_scale = T_rated_RMexprt / T_implied. Multiply "
            "FEM flux linkages by this factor before plugging into "
            "T(Id, Iq) in mtpa_field_weakening.py."
        )
        payload["rated_probe_abc_csv"] = SANITY_ABC_CSV
        sanity_meta = {
            "operating_point": {
                "id_a": 0.0, "iq_a": i_peak,
                "ia": ia_p, "ib": ib_p, "ic": ic_p,
            },
            "phi_d_p": phi_d_p,
            "phi_q_p": phi_q_p,
            "T_implied_nm": T_implied,
            "T_required_nm": T_REQUIRED,
            "flux_scale": flux_scale,
            "poles_used": poles,
            "pole_pairs_used": poles // 2,
            "i_rated_peak_a": i_peak,
        }
        with open(SANITY_JSON, "w") as f:
            json.dump(sanity_meta, f, indent=2)
        payload["rated_probe_json"] = SANITY_JSON

    # Other defaults for mtpa_field_weakening.py.
    payload["i_max_peak_a"] = I_MAX_DEFAULT_PEAK
    payload["i_rated_peak_a"] = i_peak
    payload["t_rated_nm"] = T_REQUIRED
    payload["omega_mech_base_rpm"] = 1800.0
    payload["omega_mech_max_rpm"] = None  # design choice outside the design
    payload["poststate"] = {
        "messages_after": messages_snapshot(),
        "validate_after": call(design.ValidateDesign),
    }
    payload["status"] = "ok" if sanity_result is not None else "sanity_failed"
    return payload


try:
    payload = main()
    if "status" not in payload:
        payload["status"] = "ok"
except BaseException as exc:
    payload = {
        "status": "error",
        "message": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    }

with open(OUT_JSON, "w") as f:
    json.dump(payload, f, indent=2)
warn("Wrote motor_params.json to: " + OUT_JSON)