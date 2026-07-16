"""Independent read-only, no-solve verification of the saved r9 model."""

import hashlib
import json
import os
import re
import traceback


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_NAME = "eesm_requal_direct_r9_01"
DESIGN_NAME = "EESM_2D_Direct_R9_Quarter"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r9")
BUILD_STATUS_PATH = os.path.join(OUT_DIR, "model_build_status_attempt1.json")
OUT_PATH = os.path.join(OUT_DIR, "model_verification_attempt1.json")
R8_STATUS_PATH = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_requalification_r8",
    "model_build_status_attempt1.json",
)
R8_VERIFICATION_PATH = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_requalification_r8",
    "model_verification_attempt1.json",
)
GENERATED_VBS = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "eesm_qual",
    "eesm_qual.aedtresults", "RMxprtDesign1.results",
    "DV106_SOL79_V0.MExportData", "Maxwl2DV.vbs",
)
R8_STATUS_SHA256 = "74ac19578532ddc883f1d46ab4c2acc0ca5cbee346f1e65d6078557b5d03cd64"
R8_VERIFICATION_SHA256 = "7b471ea41b17bd8c93f747c17dd55b5123c0618bbe6fd600dc00d736dbbf1c44"
GENERATED_VBS_SHA256 = "a07337b394a9bba6d78453f2478f0dba828829f19778bee65248129ded25719b"
SURFACE_APPROX_OBJECTS = [
    "Stator", "RotorYoke", "PoleAssembly_01", "OuterRegion", "Shaft",
]
SURFACE_APPROX_CONTRACT = {
    "name": "SurfApprox_Main",
    "objects": list(SURFACE_APPROX_OBJECTS),
    "surf_dev_choice": 2,
    "surf_dev": "0.09mm",
    "normal_dev_choice": 2,
    "normal_dev": "15deg",
    "aspect_ratio_choice": 1,
}


def normalize(value):
    if str(value) == "True":
        return True
    if str(value) == "False":
        return False
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return dict((str(key), normalize(item)) for key, item in value.items())
    try:
        return [normalize(item) for item in list(value)]
    except BaseException:
        return str(value)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def saved_section(project_text, name):
    pattern = r"\$begin\s+'" + re.escape(name) + r"'(.*?)\$end\s+'" + re.escape(name) + r"'"
    match = re.search(pattern, project_text, re.DOTALL)
    require(match is not None, "Saved section is missing: " + name)
    return match.group(1)


payload = {
    "status": "running", "read_only_verification": True,
    "project": PROJECT_NAME, "project_path": PROJECT_PATH,
    "design": DESIGN_NAME, "maxwell_solve_attempted": False,
    "campaign_binding_authorized": False, "task_10_authorized": False,
}
try:
    require(os.path.isfile(BUILD_STATUS_PATH), "Direct r9 build status is missing")
    require(os.path.isfile(R8_STATUS_PATH), "Immutable r8 build status is missing")
    require(os.path.isfile(R8_VERIFICATION_PATH),
            "Immutable r8 verification is missing")
    require(sha256(R8_STATUS_PATH) == R8_STATUS_SHA256,
            "Immutable r8 build-status hash drifted")
    require(sha256(R8_VERIFICATION_PATH) == R8_VERIFICATION_SHA256,
            "Immutable r8 verification hash drifted")
    with open(BUILD_STATUS_PATH, "r") as stream:
        build_status = json.load(stream)
    with open(R8_STATUS_PATH, "r") as stream:
        r8_status = json.load(stream)
    with open(R8_VERIFICATION_PATH, "r") as stream:
        r8_verification = json.load(stream)

    require(build_status.get("status") == "built", "Direct r9 build did not succeed")
    require(r8_status.get("status") == "built" and
            r8_verification.get("status") == "verified",
            "Reference r8 source is not built and independently verified")
    require(build_status.get("maxwell_solve_attempted") is False,
            "Build status claims a solve")
    require(build_status.get("Task10Authorized") is False and
            build_status.get("campaign_binding_authorized") is False,
            "r9 improperly authorizes a campaign or Task 10")
    require(build_status.get("isolated_change_from_r8") ==
            "generated_surface_approximation_only",
            "r9 isolated-change declaration drifted")

    # Exhaustively compare every r8 build-status field except the identifiers
    # that necessarily name the new immutable project/revision.  The mesh
    # contract and its evidence are the only added semantic fields.
    identity_fields = {
        "project", "project_path", "project_sha256", "design",
        "geometry_revision", "solver_revision", "isolated_change_from_r7",
    }
    added_fields = {
        "isolated_change_from_r8", "surface_approximation_contract",
        "surface_approximation_evidence", "campaign_binding_authorized",
    }
    expected_keys = (set(r8_status) - {"isolated_change_from_r7"}) | added_fields
    require(set(build_status) == expected_keys,
            "r9 build-status field set drifted from r8 plus isolated additions")
    unchanged_fields = sorted(set(r8_status) - identity_fields)
    drifted = [name for name in unchanged_fields
               if build_status.get(name) != r8_status.get(name)]
    require(not drifted, "r9 drifted from r8 outside surface approximation: "
            + ", ".join(drifted))
    require(build_status.get("surface_approximation_contract") ==
            SURFACE_APPROX_CONTRACT,
            "Surface-approximation build contract drifted")
    evidence = build_status.get("surface_approximation_evidence", {})
    require(evidence.get("generated_vbs_sha256") == GENERATED_VBS_SHA256 and
            evidence.get("generated_operation") == "SurfApprox_Main",
            "Surface-approximation evidence binding drifted")
    require(os.path.isfile(GENERATED_VBS) and
            sha256(GENERATED_VBS) == GENERATED_VBS_SHA256,
            "Generated Maxwell 2D evidence is missing or changed")

    require(os.path.isfile(PROJECT_PATH), "Direct r9 project is missing")
    project_hash = sha256(PROJECT_PATH)
    require(project_hash == build_status.get("project_sha256"),
            "Direct r9 project hash does not match build status")
    with open(PROJECT_PATH, "rb") as stream:
        project_text = stream.read().decode("latin-1")
    require(project_text.count("$begin 'SurfApprox_Main'") == 1,
            "Saved project must contain exactly one SurfApprox_Main")
    mesh_section = saved_section(project_text, "SurfApprox_Main")

    project = oDesktop.GetActiveProject()
    require(project is not None and project.GetName() == PROJECT_NAME,
            "Unexpected active project")
    design = project.SetActiveDesign(DESIGN_NAME)
    editor = design.SetActiveEditor("3D Modeler")
    boundary = design.GetModule("BoundarySetup")
    mesh = design.GetModule("MeshSetup")
    sheets = sorted(str(name) for name in list(editor.GetObjectsInGroup("Sheets")))
    require(sheets == r8_verification.get("sheets"),
            "Runtime sheet inventory drifted from verified r8")
    require(str(design.GetSolutionType()) == "Magnetostatic" and
            str(design.GetGeometryMode()) == "XY",
            "r8 Magnetostatic XY solution contract drifted")
    require(list(design.GetModule("AnalysisSetup").GetSetups()) == ["Setup_Qual"],
            "r8 setup inventory drifted")
    require(list(boundary.GetBoundaries()) == [
        "Outer_A0", "Vector Potential",
        "Quarter_Independent", "Independent",
        "Quarter_Dependent", "Dependent",
    ], "r8 boundary inventory/order drifted")
    require([str(name) for name in list(mesh.GetOperationNames("All"))] ==
            ["SurfApprox_Main"],
            "Expected exactly one saved mesh operation: SurfApprox_Main")

    expected_ids = [int(editor.GetObjectIDByName(name))
                    for name in SURFACE_APPROX_OBJECTS]
    object_match = re.search(r"Objects\(([^)]*)\)", mesh_section)
    require(object_match is not None,
            "SurfApprox_Main saved object assignments are missing")
    saved_ids = [int(value) for value in
                 re.findall(r"\d+", object_match.group(1))]
    require(saved_ids == expected_ids,
            "SurfApprox_Main saved object assignments/order drifted")
    exact_saved_settings = [
        "Type='SurfApproxBased'",
        "CurvedSurfaceApproxChoice='ManualSettings'",
        "SurfDevChoice=2", "SurfDev='0.09mm'",
        "NormalDevChoice=2", "NormalDev='15deg'",
        "AspectRatioChoice=1",
    ]
    missing_settings = [value for value in exact_saved_settings
                        if value not in mesh_section]
    require(not missing_settings,
            "SurfApprox_Main saved settings drifted: " + str(missing_settings))

    independent = saved_section(project_text, "Quarter_Independent")
    dependent = saved_section(project_text, "Quarter_Dependent")
    require("ReverseV=false" in independent and
            "ReverseU=true" in dependent and
            "SameAsMaster=false" in dependent,
            "r8 periodic-boundary directions drifted")
    outputs = design.GetModule("OutputVariable")
    require(outputs.DoesOutputVariableExist("Torque_FEM_Sector") and
            outputs.DoesOutputVariableExist("Torque_FEM") and
            "4*TorqueRotor.Torque" in project_text,
            "r8 raw-sector/manual-x4 torque contract drifted")
    require("RegionParameters" not in project_text and
            "_QuadrantClip" not in project_text,
            "r8 shared RMxprt/Band topology history drifted")
    validation = normalize(design.ValidateDesign())
    errors = normalize(oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2))
    require(validation in (0, None, True), "ValidateDesign failed: " + str(validation))
    require(not errors, "AEDT recorded design errors: " + str(errors))
    payload.update({
        "status": "verified", "project_sha256": project_hash,
        "r8_build_status_sha256": R8_STATUS_SHA256,
        "r8_verification_sha256": R8_VERIFICATION_SHA256,
        "r8_unchanged_fields": unchanged_fields,
        "surface_approximation_contract": SURFACE_APPROX_CONTRACT,
        "saved_surface_object_ids": saved_ids,
        "mesh_operations": ["SurfApprox_Main"],
        "sheet_count": len(sheets), "sheets": sheets,
        "manual_x4_scaling_preserved": True,
        "validation": validation, "errors": errors,
    })
except BaseException as exc:
    payload.update({
        "status": "error", "error": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    })
finally:
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    with open(OUT_PATH, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)
    try:
        AddWarningMessage("Direct EESM r9 verification: " + OUT_PATH)
    except BaseException:
        print(OUT_PATH)
