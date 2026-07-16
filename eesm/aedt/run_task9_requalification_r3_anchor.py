"""Run one corrected-r3 requalification anchor with five fail-closed solves.

Run this only on a fresh per-anchor copy of the verified r3 project.  The four
displaced solves hold numeric phase currents fixed and sample magnetic
coenergy at +/-1 and +/-2 mechanical degrees.  The nominal solve is last.
"""

import csv
import hashlib
import json
import math
import os
import re
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
CAMPAIGN_ROOT = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_requalification_r3_gui_recovery_20260716_01"
)
RAW_ROOT = os.path.join(CAMPAIGN_ROOT, "raw")
POINTS_PATH = os.path.join(CAMPAIGN_ROOT, "frozen_points.csv")
FREEZE_PATH = os.path.join(CAMPAIGN_ROOT, "requalification_freeze.json")
PROGRESS_PATH = os.path.join(RAW_ROOT, "diagnostic_progress.csv")
STATUS_PATH = os.path.join(RAW_ROOT, "diagnostic_status.json")
EVIDENCE_ROOT = os.path.join(RAW_ROOT, "anchor_evidence")
SESSION_MANIFEST_ROOT = os.path.join(RAW_ROOT, "session_manifests")
SESSIONS_ROOT = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "task9_r3_sessions"
)
POINTS_SHA256 = "9fec334340f777d57db639fbd2570d92ecfafa0f0bfaa1a37e0873868a9c057b"
SOURCE_PROJECT_SHA256 = "e99d4aba12ac4dc139e8797482bb54c2240a1134d277ef74ee7fcb4f19aa57a9"
CAMPAIGN_ID = "eesm_task9_torque_requal_r3_20260716"
DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"
SOLUTION_NAME = "Setup_Qual : LastAdaptive"
TORQUE_OUTPUT_NAME = "Torque_FEM"
REPORT_NAME = "EESM_Task9_R3_Flux_ABC"
POLE_PAIRS = 2
THETA_E_DEG = 180.0
MAX_NEW_ANCHORS_PER_SESSION = 1
MAX_MESH_ELEMENTS = 1950
NONCONVERGENCE_MARKER = "adaptive passes did not converge"
ROTATING_OBJECTS = (
    "Rotor", "Shaft", "Field_0", "FieldRe_0", "Bar", "Bar_Separate1",
    "Bar_Separate2",
)
PROJECT_PREFIX = "eesm_requal_r3_anchor_"
PHASE_BRANCHES = 4
OFFSETS = (-2.0, 2.0, -1.0, 1.0, 0.0)
OFFSET_LABEL = {-2.0: "m2", -1.0: "m1", 0.0: "nominal", 1.0: "p1", 2.0: "p2"}
POINT_FIELDS = (
    "PointName", "point_id", "region", "Id [A]", "Iq [A]", "If [A]",
    "purpose", "campaign_id",
)
FIELDS = (
    "PointName", "PointID", "Region", "Purpose", "Id [A]", "Iq [A]", "If [A]",
    "Ia [A]", "Ib [A]", "Ic [A]", "FluxA [Wb]", "FluxB [Wb]", "FluxC [Wb]",
    "FluxD [Wb]", "FluxQ [Wb]", "TorqueVirtualFEM [N*m]",
    "TorqueController [N*m]", "TorquePhaseFlux [N*m]",
    "TorqueCoenergy [N*m]", "TorqueCoenergyCoarse [N*m]",
    "TorqueCoenergyFEMFine [N*m]", "TorqueCoenergyFEMCoarse [N*m]",
    "CoenergyM2 [J]", "CoenergyM1 [J]", "CoenergyP1 [J]", "CoenergyP2 [J]",
    "CoenergyAngleM2 [deg]", "CoenergyAngleM1 [deg]",
    "CoenergyAngleP1 [deg]", "CoenergyAngleP2 [deg]",
    "Project", "Design", "Setup", "SourceProjectSHA256", "PointsSHA256",
    "SolverStatus", "SolverMessages", "RawABCFluxPath", "EvidenceManifestPath",
)
SECTOR_SCALE = 1.0
RAW_SECTOR_FIELDS = ()
MODE = os.environ.get("EESM_REQUAL_MODE", "r3")
if MODE == "r4":
    CAMPAIGN_ROOT = os.path.join(
        REPO_ROOT, "out", "eesm", "task9_requalification_r4_attempt4_20260716"
    )
    RAW_ROOT = os.path.join(CAMPAIGN_ROOT, "raw")
    POINTS_PATH = os.path.join(CAMPAIGN_ROOT, "frozen_points.csv")
    FREEZE_PATH = os.path.join(CAMPAIGN_ROOT, "requalification_freeze.json")
    PROGRESS_PATH = os.path.join(RAW_ROOT, "diagnostic_progress.csv")
    STATUS_PATH = os.path.join(RAW_ROOT, "diagnostic_status.json")
    EVIDENCE_ROOT = os.path.join(RAW_ROOT, "anchor_evidence")
    SESSION_MANIFEST_ROOT = os.path.join(RAW_ROOT, "session_manifests")
    SESSIONS_ROOT = os.path.join(
        REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "task9_r4_sessions"
    )
    POINTS_SHA256 = "5bb921f6304fcb35fee992ce3801a9c4ddad1b7aac696ba4d5740b183f962e38"
    SOURCE_PROJECT_SHA256 = "4ff65ae2c158679c8caa6ece2d38a86b931cf6d0e945ea745aaa6714e03236a7"
    CAMPAIGN_ID = "eesm_task9_torque_requal_r4_20260716"
    DESIGN_NAME = "EESM_2D_Direct_R4"
    ROTATING_OBJECTS = tuple(
        ["Rotor", "Shaft"] + [
            "Field_P%02d_%s" % (pole, side)
            for pole in range(1, 5) for side in ("NegT", "PosT")
        ]
    )
    PROJECT_PREFIX = "eesm_requal_r4_anchor_"
    PHASE_BRANCHES = 1
elif MODE == "r5":
    CAMPAIGN_ROOT = os.path.abspath(os.environ.get(
        "EESM_R5_CAMPAIGN_ROOT",
        os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r5_20260716"),
    ))
    RAW_ROOT = os.path.join(CAMPAIGN_ROOT, "raw")
    POINTS_PATH = os.path.join(CAMPAIGN_ROOT, "frozen_points.csv")
    FREEZE_PATH = os.path.join(CAMPAIGN_ROOT, "requalification_freeze.json")
    if not os.path.isfile(FREEZE_PATH):
        raise RuntimeError("R5 qualification must be frozen before the runner is launched")
    with open(FREEZE_PATH, "r") as stream:
        _r5_freeze = json.load(stream)
    POINTS_SHA256 = str(_r5_freeze.get("anchors_sha256", ""))
    SOURCE_PROJECT_SHA256 = "4fccd71493d0864db866ff0c55d01fe0e3fb304da76f5feb55ef3fe2ffabe830"
    CAMPAIGN_ID = str(_r5_freeze.get("campaign_id", ""))
    if (len(POINTS_SHA256) != 64 or not CAMPAIGN_ID
            or _r5_freeze.get("project_sha256") != SOURCE_PROJECT_SHA256):
        raise RuntimeError("Frozen r5 qualification metadata is incomplete or source-bound incorrectly")
    PROGRESS_PATH = os.path.join(RAW_ROOT, "diagnostic_progress.csv")
    STATUS_PATH = os.path.join(RAW_ROOT, "diagnostic_status.json")
    EVIDENCE_ROOT = os.path.join(RAW_ROOT, "anchor_evidence")
    SESSION_MANIFEST_ROOT = os.path.join(RAW_ROOT, "session_manifests")
    SESSIONS_ROOT = os.path.join(
        REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "task9_r5_sessions"
    )
    DESIGN_NAME = "EESM_2D_Direct_R5_Quarter"
    TORQUE_OUTPUT_NAME = "Torque_FEM"
    ROTATING_OBJECTS = (
        "PoleAssembly_01", "Field_P01_NegT", "Field_P01_PosT",
    )
    PROJECT_PREFIX = "eesm_requal_r5_anchor_"
    PHASE_BRANCHES = 1
    SECTOR_SCALE = 4.0
    RAW_SECTOR_FIELDS = (
        "RawSectorFluxA [Wb]", "RawSectorFluxB [Wb]", "RawSectorFluxC [Wb]",
        "RawSectorCoenergyM2 [J]", "RawSectorCoenergyM1 [J]",
        "RawSectorCoenergyP1 [J]", "RawSectorCoenergyP2 [J]",
        "TorqueFEMSector [N*m]", "SectorToFullScale [count]",
    )
    FIELDS = FIELDS[:-2] + RAW_SECTOR_FIELDS + FIELDS[-2:]
elif MODE == "r6":
    CAMPAIGN_ROOT = os.path.abspath(os.environ.get(
        "EESM_R6_CAMPAIGN_ROOT",
        os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r6_attempt1_20260716"),
    ))
    RAW_ROOT = os.path.join(CAMPAIGN_ROOT, "raw")
    POINTS_PATH = os.path.join(CAMPAIGN_ROOT, "frozen_points.csv")
    FREEZE_PATH = os.path.join(CAMPAIGN_ROOT, "requalification_freeze.json")
    if not os.path.isfile(FREEZE_PATH):
        raise RuntimeError("R6 qualification must be frozen before the runner is launched")
    with open(FREEZE_PATH, "r") as stream:
        _r6_freeze = json.load(stream)
    POINTS_SHA256 = str(_r6_freeze.get("anchors_sha256", ""))
    SOURCE_PROJECT_SHA256 = "404a4b6f5a7e91f9c3bd69087c5a50e43ac51b22b899cbbb168e5e55feffbbcd"
    CAMPAIGN_ID = str(_r6_freeze.get("campaign_id", ""))
    if (len(POINTS_SHA256) != 64 or not CAMPAIGN_ID
            or _r6_freeze.get("project_sha256") != SOURCE_PROJECT_SHA256):
        raise RuntimeError("Frozen r6 qualification metadata is incomplete or source-bound incorrectly")
    PROGRESS_PATH = os.path.join(RAW_ROOT, "diagnostic_progress.csv")
    STATUS_PATH = os.path.join(RAW_ROOT, "diagnostic_status.json")
    EVIDENCE_ROOT = os.path.join(RAW_ROOT, "anchor_evidence")
    SESSION_MANIFEST_ROOT = os.path.join(RAW_ROOT, "session_manifests")
    SESSIONS_ROOT = os.path.join(
        REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "task9_r6_sessions"
    )
    DESIGN_NAME = "EESM_2D_Direct_R6_Quarter"
    TORQUE_OUTPUT_NAME = "Torque_FEM"
    ROTATING_OBJECTS = (
        "PoleAssembly_01", "Field_P01_NegT", "Field_P01_PosT",
    )
    PROJECT_PREFIX = "eesm_requal_r6_anchor_"
    PHASE_BRANCHES = 1
    SECTOR_SCALE = 4.0
    RAW_SECTOR_FIELDS = (
        "RawSectorFluxA [Wb]", "RawSectorFluxB [Wb]", "RawSectorFluxC [Wb]",
        "RawSectorCoenergyM2 [J]", "RawSectorCoenergyM1 [J]",
        "RawSectorCoenergyP1 [J]", "RawSectorCoenergyP2 [J]",
        "TorqueFEMSector [N*m]", "SectorToFullScale [count]",
    )
    FIELDS = FIELDS[:-2] + RAW_SECTOR_FIELDS + FIELDS[-2:]
elif MODE == "r7":
    CAMPAIGN_ROOT = os.path.abspath(os.environ.get(
        "EESM_R7_CAMPAIGN_ROOT",
        os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r7_attempt1_20260716"),
    ))
    RAW_ROOT = os.path.join(CAMPAIGN_ROOT, "raw")
    POINTS_PATH = os.path.join(CAMPAIGN_ROOT, "frozen_points.csv")
    FREEZE_PATH = os.path.join(CAMPAIGN_ROOT, "requalification_freeze.json")
    if not os.path.isfile(FREEZE_PATH):
        raise RuntimeError("R7 qualification must be frozen before the runner is launched")
    with open(FREEZE_PATH, "r") as stream:
        _r7_freeze = json.load(stream)
    POINTS_SHA256 = str(_r7_freeze.get("anchors_sha256", ""))
    SOURCE_PROJECT_SHA256 = "527d2430823b981f6eff753d8044abc061029d12446c9b17196d16c3acd53bf1"
    CAMPAIGN_ID = str(_r7_freeze.get("campaign_id", ""))
    if (len(POINTS_SHA256) != 64 or not CAMPAIGN_ID
            or _r7_freeze.get("project_sha256") != SOURCE_PROJECT_SHA256):
        raise RuntimeError("Frozen r7 qualification metadata is incomplete or source-bound incorrectly")
    PROGRESS_PATH = os.path.join(RAW_ROOT, "diagnostic_progress.csv")
    STATUS_PATH = os.path.join(RAW_ROOT, "diagnostic_status.json")
    EVIDENCE_ROOT = os.path.join(RAW_ROOT, "anchor_evidence")
    SESSION_MANIFEST_ROOT = os.path.join(RAW_ROOT, "session_manifests")
    SESSIONS_ROOT = os.path.join(
        REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "task9_r7_sessions"
    )
    DESIGN_NAME = "EESM_2D_Direct_R7_Quarter"
    TORQUE_OUTPUT_NAME = "Torque_FEM"
    ROTATING_OBJECTS = (
        "PoleAssembly_01", "Field_P01_NegT", "Field_P01_PosT",
    )
    PROJECT_PREFIX = "eesm_requal_r7_anchor_"
    PHASE_BRANCHES = 1
    SECTOR_SCALE = 4.0
    RAW_SECTOR_FIELDS = (
        "RawSectorFluxA [Wb]", "RawSectorFluxB [Wb]", "RawSectorFluxC [Wb]",
        "RawSectorCoenergyM2 [J]", "RawSectorCoenergyM1 [J]",
        "RawSectorCoenergyP1 [J]", "RawSectorCoenergyP2 [J]",
        "TorqueFEMSector [N*m]", "SectorToFullScale [count]",
    )
    FIELDS = FIELDS[:-2] + RAW_SECTOR_FIELDS + FIELDS[-2:]
elif MODE == "r8":
    CAMPAIGN_ROOT = os.path.abspath(os.environ.get(
        "EESM_R8_CAMPAIGN_ROOT",
        os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r8_attempt1_20260716"),
    ))
    RAW_ROOT = os.path.join(CAMPAIGN_ROOT, "raw")
    POINTS_PATH = os.path.join(CAMPAIGN_ROOT, "frozen_points.csv")
    FREEZE_PATH = os.path.join(CAMPAIGN_ROOT, "requalification_freeze.json")
    if not os.path.isfile(FREEZE_PATH):
        raise RuntimeError("R8 qualification must be frozen before the runner is launched")
    with open(FREEZE_PATH, "r") as stream:
        _r8_freeze = json.load(stream)
    POINTS_SHA256 = str(_r8_freeze.get("anchors_sha256", ""))
    SOURCE_PROJECT_SHA256 = "28defa3863eb863de5b0a0deed826fc4a686116acd2c9d84804d93ef72cb0d98"
    CAMPAIGN_ID = str(_r8_freeze.get("campaign_id", ""))
    if (len(POINTS_SHA256) != 64 or not CAMPAIGN_ID
            or _r8_freeze.get("project_sha256") != SOURCE_PROJECT_SHA256
            or _r8_freeze.get("model_build_status_sha256") !=
            "74ac19578532ddc883f1d46ab4c2acc0ca5cbee346f1e65d6078557b5d03cd64"
            or _r8_freeze.get("model_status_sha256") !=
            "7b471ea41b17bd8c93f747c17dd55b5123c0618bbe6fd600dc00d736dbbf1c44"
            or _r8_freeze.get("post_verification_crash_evidence", {}).get("sha256") !=
            "9eb5b2afbbe90d44459305d3d00455a7bc1512d71aff1726f387fa1d81d2e062"):
        raise RuntimeError("Frozen r8 qualification metadata is incomplete or source-bound incorrectly")
    PROGRESS_PATH = os.path.join(RAW_ROOT, "diagnostic_progress.csv")
    STATUS_PATH = os.path.join(RAW_ROOT, "diagnostic_status.json")
    EVIDENCE_ROOT = os.path.join(RAW_ROOT, "anchor_evidence")
    SESSION_MANIFEST_ROOT = os.path.join(RAW_ROOT, "session_manifests")
    SESSIONS_ROOT = os.path.join(
        REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "task9_r8_sessions"
    )
    DESIGN_NAME = "EESM_2D_Direct_R8_Quarter"
    TORQUE_OUTPUT_NAME = "Torque_FEM"
    ROTATING_OBJECTS = (
        "PoleAssembly_01", "Field_P01_NegT", "Field_P01_PosT",
    )
    PROJECT_PREFIX = "eesm_requal_r8_anchor_"
    PHASE_BRANCHES = 1
    SECTOR_SCALE = 4.0
    RAW_SECTOR_FIELDS = (
        "RawSectorFluxA [Wb]", "RawSectorFluxB [Wb]", "RawSectorFluxC [Wb]",
        "RawSectorCoenergyM2 [J]", "RawSectorCoenergyM1 [J]",
        "RawSectorCoenergyP1 [J]", "RawSectorCoenergyP2 [J]",
        "TorqueFEMSector [N*m]", "SectorToFullScale [count]",
    )
    FIELDS = FIELDS[:-2] + RAW_SECTOR_FIELDS + FIELDS[-2:]


def normalize(value):
    if isinstance(value, bool):
        return bool(value)
    if value is None or isinstance(value, (str, int, float)):
        return value
    if isinstance(value, dict):
        return dict((str(key), normalize(item)) for key, item in value.items())
    try:
        return [normalize(item) for item in list(value)]
    except BaseException:
        return str(value)


def call(fn):
    try:
        raw = fn()
        return {"ok": True, "value": normalize(raw), "raw": raw}
    except BaseException as exc:
        return {
            "ok": False, "error": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-8:],
        }


def required(fn, label):
    outcome = call(fn)
    if not outcome["ok"]:
        raise RuntimeError(label + ": " + outcome["error"])
    return outcome["raw"]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def artifact_record(path):
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError("Evidence artifact missing or empty: " + path)
    return {
        "path": os.path.abspath(path),
        "size_bytes": os.path.getsize(path),
        "sha256": sha256_file(path),
    }


def write_status(payload):
    if not os.path.isdir(RAW_ROOT):
        os.makedirs(RAW_ROOT)
    with open(STATUS_PATH, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)


def mark(payload, point_name, stage):
    payload["active_point"] = point_name
    payload["stage"] = stage
    write_status(payload)


def finite(value, label):
    try:
        number = float(str(value).split()[0])
    except BaseException:
        raise RuntimeError(label + " was not numeric")
    if math.isnan(number) or math.isinf(number):
        raise RuntimeError(label + " was non-finite")
    return number


def read_points():
    if sha256_file(POINTS_PATH) != POINTS_SHA256:
        raise RuntimeError("Frozen r3 anchor hash mismatch")
    with open(POINTS_PATH, "r") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != POINT_FIELDS:
            raise RuntimeError("Malformed frozen r3 anchor header")
        rows = list(reader)
    if len(rows) != 10 or any(row["campaign_id"] != CAMPAIGN_ID for row in rows):
        raise RuntimeError("Invalid frozen r3 anchor campaign")
    return rows


def read_progress(points):
    if not os.path.isfile(PROGRESS_PATH):
        return [], set()
    with open(PROGRESS_PATH, "r") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise RuntimeError("Refusing resume: malformed r3 progress header")
        rows = list(reader)
    expected = dict((row["point_id"], row) for row in points)
    seen = set()
    for row in rows:
        point_id = row.get("PointID", "")
        if point_id not in expected or point_id in seen:
            raise RuntimeError("Refusing resume: unknown or duplicate r3 point")
        if row.get("SolverStatus") != "converged":
            raise RuntimeError("Refusing resume: prior r3 row failed")
        frozen = expected[point_id]
        if (row.get("PointName") != frozen["PointName"]
                or any(float(row[key]) != float(frozen[key])
                       for key in ("Id [A]", "Iq [A]", "If [A]"))
                or row.get("Project") != PROJECT_PREFIX + frozen["PointName"]
                or row.get("Design") != DESIGN_NAME
                or row.get("Setup") != SETUP_NAME
                or row.get("SourceProjectSHA256") != SOURCE_PROJECT_SHA256
                or row.get("PointsSHA256") != POINTS_SHA256):
            raise RuntimeError("Refusing resume: prior r3 row drifted")
        for key in ("RawABCFluxPath", "EvidenceManifestPath"):
            path = row.get(key, "")
            if not os.path.isfile(path) or os.path.getsize(path) <= 0:
                raise RuntimeError("Refusing resume: missing r3 evidence")
        with open(row["EvidenceManifestPath"], "r") as stream:
            manifest = json.load(stream)
        if (manifest.get("point") != frozen
                or manifest.get("source_project_sha256") != SOURCE_PROJECT_SHA256
                or manifest.get("points_sha256") != POINTS_SHA256):
            raise RuntimeError("Refusing resume: evidence manifest provenance drifted")
        records = manifest.get("artifacts", [])
        if len(records) != 16:
            raise RuntimeError("Refusing resume: evidence artifact inventory drifted")
        for record in records:
            path = record.get("path", "")
            if (not os.path.isfile(path)
                    or os.path.getsize(path) != record.get("size_bytes")
                    or sha256_file(path) != record.get("sha256")):
                raise RuntimeError("Refusing resume: evidence artifact hash drifted")
        if MODE in ("r5", "r6", "r7", "r8"):
            if finite(row["SectorToFullScale [count]"], "sector scale") != SECTOR_SCALE:
                raise RuntimeError("Refusing resume: quarter-sector scale drifted")
            for full_key, raw_key in zip(
                    ("FluxA [Wb]", "FluxB [Wb]", "FluxC [Wb]",
                     "CoenergyM2 [J]", "CoenergyM1 [J]", "CoenergyP1 [J]", "CoenergyP2 [J]"),
                    ("RawSectorFluxA [Wb]", "RawSectorFluxB [Wb]", "RawSectorFluxC [Wb]",
                     "RawSectorCoenergyM2 [J]", "RawSectorCoenergyM1 [J]",
                     "RawSectorCoenergyP1 [J]", "RawSectorCoenergyP2 [J]")):
                if abs(finite(row[full_key], full_key)
                       - SECTOR_SCALE * finite(row[raw_key], raw_key)) > 1e-8:
                    raise RuntimeError("Refusing resume: quarter-sector evidence scaling drifted")
            if abs(finite(row["TorqueVirtualFEM [N*m]"], "Torque_FEM")
                   - SECTOR_SCALE * finite(row["TorqueFEMSector [N*m]"],
                                           "Torque_FEM_Sector")) > 1e-8:
                raise RuntimeError("Refusing resume: quarter-sector torque scaling identity drifted")
        seen.add(point_id)
    return rows, seen


def append_result(result):
    exists = os.path.isfile(PROGRESS_PATH) and os.path.getsize(PROGRESS_PATH) > 0
    with open(PROGRESS_PATH, "ab") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\r\n")
        if not exists:
            writer.writeheader()
        writer.writerow(result)


def phase_currents(id_a, iq_a):
    theta = math.pi
    angles = (theta, theta - 2.0 * math.pi / 3.0, theta + 2.0 * math.pi / 3.0)
    return tuple(id_a * math.cos(angle) - iq_a * math.sin(angle) for angle in angles)


def dq_flux(phi_a, phi_b, phi_c):
    theta = math.pi
    angles = (theta, theta - 2.0 * math.pi / 3.0, theta + 2.0 * math.pi / 3.0)
    abc = (phi_a, phi_b, phi_c)
    phi_d = (2.0 / 3.0) * sum(value * math.cos(angle) for value, angle in zip(abc, angles))
    phi_q = -(2.0 / 3.0) * sum(value * math.sin(angle) for value, angle in zip(abc, angles))
    return phi_d, phi_q


def set_local_variables(design, values):
    changed = [["NAME:" + name, "Value:=", value] for name, value in values.items()]
    required(lambda: design.ChangeProperty([
        "NAME:AllTabs", ["NAME:LocalVariableTab", ["NAME:PropServers", "LocalVariables"],
        ["NAME:ChangedProps"] + changed],
    ]), "Change local qualification variables")


def edit_winding(boundary, name, current, branches):
    required(lambda: boundary.EditWindingGroup(name, [
        "NAME:" + name, "Type:=", "Current", "IsSolid:=", False,
        "Current:=", current, "Resistance:=", "0ohm", "Inductance:=", "0nH",
        "Voltage:=", "0V", "ParallelBranchesNum:=", branches, "Phase:=", "0deg",
    ]), "Edit winding " + name)


def apply_numeric_currents(design, point):
    id_a = float(point["Id [A]"])
    iq_a = float(point["Iq [A]"])
    if_a = float(point["If [A]"])
    abc = phase_currents(id_a, iq_a)
    set_local_variables(design, {
        "Id": "%.12gA" % id_a, "Iq": "%.12gA" % iq_a, "If": "%.12gA" % if_a,
        "theta_e": "180deg",
    })
    boundary = required(lambda: design.GetModule("BoundarySetup"), "Get BoundarySetup")
    for name, value in zip(("PhaseA", "PhaseB", "PhaseC"), abc):
        edit_winding(boundary, name, "%.12gA" % value, PHASE_BRANCHES)
    edit_winding(boundary, "Field", "%.12gA" % if_a, 1)
    return abc


def restore_parametric(design, originals):
    set_local_variables(design, originals)
    boundary = required(lambda: design.GetModule("BoundarySetup"), "Get BoundarySetup")
    for name, expression in (
        ("PhaseA", "I_phase_a"), ("PhaseB", "I_phase_b"),
        ("PhaseC", "I_phase_c"), ("Field", "If"),
    ):
        edit_winding(boundary, name, expression, 1 if name == "Field" else PHASE_BRANCHES)
    for name, expected in originals.items():
        actual = str(required(lambda name=name: design.GetVariableValue(name), "Read restored " + name))
        if actual != expected:
            raise RuntimeError("Restored variable mismatch for " + name + ": " + actual)


def rotate(editor, degrees):
    if degrees == 0.0:
        return
    required(lambda: editor.Rotate(
        ["NAME:Selections", "Selections:=", ",".join(ROTATING_OBJECTS)],
        ["NAME:RotateParameters", "CoordinateSystemID:=", -1,
         "RotateAxis:=", "Z", "RotateAngle:=", "%.12gdeg" % degrees],
    ), "Rotate corrected rotor assembly")


def positive_integers(text):
    return [int(item) for item in re.findall(r"(?<![.\d])-?\d+(?![.\d])", text)
            if int(item) > 0]


def export_solver_evidence(design, anchor_dir, label):
    mesh_path = os.path.join(anchor_dir, label + "_mesh.ms")
    conv_path = os.path.join(anchor_dir, label + "_convergence.conv")
    for path in (mesh_path, conv_path):
        if os.path.exists(path):
            raise RuntimeError("Refusing evidence overwrite: " + path)
    required(lambda: design.ExportMeshStats(SETUP_NAME, "", mesh_path, True),
             "Export mesh evidence")
    required(lambda: design.ExportConvergence(SETUP_NAME, "", conv_path, True),
             "Export convergence evidence")
    with open(mesh_path, "r") as stream:
        total_lines = [line for line in stream.readlines() if "total" in line.lower()]
    mesh_values = []
    for line in total_lines:
        mesh_values.extend(positive_integers(line))
    if not mesh_values:
        raise RuntimeError("Unable to parse mesh evidence")
    with open(conv_path, "r") as stream:
        conv_lines = stream.readlines()
    pass_values = []
    in_summary = False
    for line in conv_lines:
        lowered = line.lower()
        if "number of passes" in lowered:
            in_summary = True
            continue
        if in_summary and "completed" in lowered:
            pass_values.extend(positive_integers(line))
            break
    if not pass_values:
        raise RuntimeError("Unable to parse convergence evidence")
    mesh_count = max(mesh_values)
    if mesh_count > MAX_MESH_ELEMENTS:
        raise RuntimeError("AEDT Student mesh limit exceeded: " + str(mesh_count))
    return {
        "mesh_path": mesh_path, "convergence_path": conv_path,
        "mesh_elements": mesh_count, "adaptive_passes": max(pass_values),
    }


def write_coenergy(design, path):
    if os.path.exists(path):
        raise RuntimeError("Refusing coenergy overwrite: " + path)
    fields = required(lambda: design.GetModule("FieldsReporter"), "Get FieldsReporter")
    try:
        fields.CalcStack("clear")
        fields.EnterQty("coEnergy")
        fields.EnterVol("AllObjects")
        fields.CalcOp("Integrate")
        fields.CalculatorWrite(path, ["Solution:=", SOLUTION_NAME], [])
    finally:
        try:
            fields.CalcStack("clear")
        except BaseException:
            pass
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError("Coenergy evidence missing")
    with open(path, "r") as stream:
        lines = [line.strip() for line in stream.readlines() if line.strip()]
    if not lines:
        raise RuntimeError("Coenergy evidence empty")
    return finite(lines[-1], "coEnergy")


def export_flux(design, path):
    if os.path.exists(path):
        raise RuntimeError("Refusing ABC flux overwrite")
    report = required(lambda: design.GetModule("ReportSetup"), "Get ReportSetup")
    if REPORT_NAME in list(required(report.GetAllReportNames, "Get report names")):
        required(lambda: report.DeleteReports([REPORT_NAME]), "Delete owned report")
    expressions = ["FluxLinkage(PhaseA)", "FluxLinkage(PhaseB)", "FluxLinkage(PhaseC)"]
    try:
        required(lambda: report.CreateReport(
            REPORT_NAME, "Magnetostatic", "Data Table", SOLUTION_NAME, [],
            ["fractions:=", ["All"]],
            ["X Component:=", "fractions", "Y Component:=", expressions],
        ), "Create ABC flux report")
        required(lambda: report.ExportToFile(REPORT_NAME, path), "Export ABC flux")
    finally:
        try:
            if REPORT_NAME in list(report.GetAllReportNames()):
                report.DeleteReports([REPORT_NAME])
        except BaseException:
            pass
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError("ABC flux evidence missing or empty")
    with open(path, "r") as stream:
        rows = list(csv.reader(stream))
    if len(rows) < 2 or len(rows[-1]) < 4:
        raise RuntimeError("Incomplete ABC flux evidence")
    return tuple(finite(value, "ABC flux") for value in rows[-1][1:4])


def solve_at_offset(design, editor, project_name, anchor_dir, offset, state):
    label = OFFSET_LABEL[offset]
    if offset:
        rotate(editor, offset)
        state["angle"] = offset
    try:
        oDesktop.ClearMessages(project_name, DESIGN_NAME, 3)
        solve = call(lambda: design.Analyze(SETUP_NAME))
        if not solve["ok"] or solve["value"] not in (0, None):
            raise RuntimeError("Analyze failed: " + str(solve.get("error") or solve["value"]))
        evidence = export_solver_evidence(design, anchor_dir, label)
        errors = normalize(required(lambda: oDesktop.GetMessages(project_name, DESIGN_NAME, 2),
                                    "Read solve errors")) or []
        warnings = normalize(required(lambda: oDesktop.GetMessages(project_name, DESIGN_NAME, 1),
                                      "Read solve warnings")) or []
        if errors:
            raise RuntimeError("AEDT solve errors: " + json.dumps(errors))
        if any(NONCONVERGENCE_MARKER in str(item).lower() for item in warnings):
            raise RuntimeError("AEDT adaptive convergence criteria were not met")
        evidence["messages"] = {"errors": errors, "warnings": warnings,
                                "solve_return": solve["value"]}
        coenergy_path = os.path.join(anchor_dir, label + "_coenergy.fld")
        evidence["coenergy_path"] = coenergy_path
        evidence["coenergy_j"] = write_coenergy(design, coenergy_path)
        return evidence
    finally:
        if offset and state.get("angle"):
            rotate(editor, -state["angle"])
            state["angle"] = 0.0


payload = {
    "status": "running", "stage": "preflight", "active_point": None,
    "completed": [], "failure": None, "campaign_id": CAMPAIGN_ID,
    "points_sha256": POINTS_SHA256, "source_project_sha256": SOURCE_PROJECT_SHA256,
    "sector_to_full_scale": SECTOR_SCALE,
    "raw_sector_evidence_preserved": MODE in ("r5", "r6", "r7", "r8"),
    "max_new_anchors_per_session": MAX_NEW_ANCHORS_PER_SESSION,
    "new_task9_campaign_authorized": False, "task_10_authorized": False,
}
result = None
state = {"angle": 0.0}
restoration_error = None
try:
    if not os.path.isfile(FREEZE_PATH):
        raise RuntimeError("Missing frozen r3 requalification contract")
    with open(FREEZE_PATH, "r") as stream:
        freeze = json.load(stream)
    if (freeze.get("anchors_sha256") != POINTS_SHA256
            or freeze.get("project_sha256") != SOURCE_PROJECT_SHA256
            or freeze.get("acceptance_frozen_before_solve") is not True):
        raise RuntimeError("Frozen r3 requalification contract drifted")
    points = read_points()
    progress_rows, done = read_progress(points)
    payload["completed"] = [row["PointName"] for row in progress_rows]
    next_points = [point for point in points if point["point_id"] not in done]
    if not next_points:
        payload.update({"status": "complete", "stage": "idle"})
    else:
        point = next_points[0]
        expected_project_name = PROJECT_PREFIX + point["PointName"]
        expected_project_path = os.path.abspath(os.path.join(
            SESSIONS_ROOT, expected_project_name, expected_project_name + ".aedt"
        ))
        session_manifest_path = os.path.join(
            SESSION_MANIFEST_ROOT, point["PointName"] + ".json"
        )
        if not os.path.isfile(session_manifest_path):
            raise RuntimeError("Missing prepared session manifest")
        with open(session_manifest_path, "r") as stream:
            session_manifest = json.load(stream)
        if (session_manifest.get("status") != "prepared"
                or session_manifest.get("project_name") != expected_project_name
                or os.path.normcase(os.path.abspath(session_manifest.get("project_path", "")))
                    != os.path.normcase(expected_project_path)
                or session_manifest.get("source_project_sha256") != SOURCE_PROJECT_SHA256
                or session_manifest.get("points_sha256") != POINTS_SHA256
                or session_manifest.get("completed_before_session") != len(progress_rows)
                or session_manifest.get("point") != point):
            raise RuntimeError("Prepared session manifest drifted")
        project = required(oDesktop.GetActiveProject, "Get active project")
        if project is None or project.GetName() != expected_project_name:
            raise RuntimeError("Active project must be " + expected_project_name)
        project_path = os.path.join(str(project.GetPath()), project.GetName() + ".aedt")
        if os.path.normcase(os.path.abspath(project_path)) != os.path.normcase(expected_project_path):
            raise RuntimeError("Active project path is not the prepared immutable session copy")
        if sha256_file(project_path) != SOURCE_PROJECT_SHA256:
            raise RuntimeError("Fresh anchor project hash does not match verified r3 source")
        design = required(lambda: project.SetActiveDesign(DESIGN_NAME), "Activate r3 design")
        if str(design.GetSolutionType()) != "Magnetostatic" or str(design.GetGeometryMode()) != "XY":
            raise RuntimeError("Active anchor design is not Magnetostatic XY")
        if list(design.GetModule("AnalysisSetup").GetSetups()) != [SETUP_NAME]:
            raise RuntimeError("Active anchor setup drifted")
        editor = required(lambda: design.SetActiveEditor("3D Modeler"), "Get 3D Modeler")
        objects = set(editor.GetObjectsInGroup("Sheets"))
        if not set(ROTATING_OBJECTS).issubset(objects):
            raise RuntimeError("Rotating assembly objects are incomplete")
        originals = dict((name, str(design.GetVariableValue(name)))
                         for name in ("Id", "Iq", "If", "theta_e"))
        if originals != {"Id": "0A", "Iq": "0A", "If": "0A", "theta_e": "180deg"}:
            raise RuntimeError("Fresh anchor variables are not at frozen nominal values: " + str(originals))
        anchor_dir = os.path.join(EVIDENCE_ROOT, point["PointName"])
        if os.path.exists(anchor_dir):
            raise RuntimeError("Anchor evidence already exists; refusing overwrite")
        os.makedirs(anchor_dir)
        result = dict((name, "") for name in FIELDS)
        result.update({
            "PointName": point["PointName"], "PointID": point["point_id"],
            "Region": point["region"], "Purpose": point["purpose"],
            "Id [A]": point["Id [A]"], "Iq [A]": point["Iq [A]"], "If [A]": point["If [A]"],
            "Project": expected_project_name, "Design": DESIGN_NAME, "Setup": SETUP_NAME,
            "SourceProjectSHA256": SOURCE_PROJECT_SHA256, "PointsSHA256": POINTS_SHA256,
            "CoenergyAngleM2 [deg]": -2.0, "CoenergyAngleM1 [deg]": -1.0,
            "CoenergyAngleP1 [deg]": 1.0, "CoenergyAngleP2 [deg]": 2.0,
        })
        mark(payload, point["PointName"], "apply_fixed_currents")
        abc = apply_numeric_currents(design, point)
        result["Ia [A]"], result["Ib [A]"], result["Ic [A]"] = abc
        solve_evidence = {}
        for offset in OFFSETS:
            mark(payload, point["PointName"], "solve_" + OFFSET_LABEL[offset])
            solve_evidence[OFFSET_LABEL[offset]] = solve_at_offset(
                design, editor, expected_project_name, anchor_dir, offset, state
            )
        raw_w_m2 = solve_evidence["m2"]["coenergy_j"]
        raw_w_m1 = solve_evidence["m1"]["coenergy_j"]
        raw_w_p1 = solve_evidence["p1"]["coenergy_j"]
        raw_w_p2 = solve_evidence["p2"]["coenergy_j"]
        w_m2, w_m1, w_p1, w_p2 = (
            SECTOR_SCALE * value
            for value in (raw_w_m2, raw_w_m1, raw_w_p1, raw_w_p2)
        )
        h = math.pi / 180.0
        torque_fem_fine = (w_p1 - w_m1) / (2.0 * h)
        torque_fem_coarse = (w_p2 - w_m2) / (4.0 * h)
        result.update({
            "CoenergyM2 [J]": w_m2, "CoenergyM1 [J]": w_m1,
            "CoenergyP1 [J]": w_p1, "CoenergyP2 [J]": w_p2,
            "TorqueCoenergyFEMFine [N*m]": torque_fem_fine,
            "TorqueCoenergyFEMCoarse [N*m]": torque_fem_coarse,
            "TorqueCoenergy [N*m]": -torque_fem_fine,
            "TorqueCoenergyCoarse [N*m]": -torque_fem_coarse,
        })
        if MODE in ("r5", "r6", "r7", "r8"):
            result.update({
                "RawSectorCoenergyM2 [J]": raw_w_m2,
                "RawSectorCoenergyM1 [J]": raw_w_m1,
                "RawSectorCoenergyP1 [J]": raw_w_p1,
                "RawSectorCoenergyP2 [J]": raw_w_p2,
                "SectorToFullScale [count]": SECTOR_SCALE,
            })
        mark(payload, point["PointName"], "nominal_flux_and_torque")
        flux_path = os.path.join(
            anchor_dir, "nominal_flux_abc_sector.csv" if MODE in ("r5", "r6", "r7", "r8") else "nominal_flux_abc.csv"
        )
        raw_phi_a, raw_phi_b, raw_phi_c = export_flux(design, flux_path)
        result["RawABCFluxPath"] = flux_path
        if MODE in ("r5", "r6", "r7", "r8"):
            result.update({
                "RawSectorFluxA [Wb]": raw_phi_a,
                "RawSectorFluxB [Wb]": raw_phi_b,
                "RawSectorFluxC [Wb]": raw_phi_c,
            })
        phi_a, phi_b, phi_c = (
            SECTOR_SCALE * value for value in (raw_phi_a, raw_phi_b, raw_phi_c)
        )
        phi_d, phi_q = dq_flux(phi_a, phi_b, phi_c)
        torque_phase = 1.5 * POLE_PAIRS * (
            phi_d * float(point["Iq [A]"]) - phi_q * float(point["Id [A]"])
        )
        output_variables = design.GetModule("OutputVariable")
        torque_virtual = finite(required(lambda: output_variables.GetOutputVariableValue(
            TORQUE_OUTPUT_NAME, "", SOLUTION_NAME, "Magnetostatic", []),
            "Read Torque_FEM"), TORQUE_OUTPUT_NAME)
        torque_sector = None
        torque_scaling_error = 0.0
        if MODE in ("r5", "r6", "r7", "r8"):
            torque_sector = finite(required(lambda: output_variables.GetOutputVariableValue(
                "Torque_FEM_Sector", "", SOLUTION_NAME, "Magnetostatic", []),
                "Read Torque_FEM_Sector"), "Torque_FEM_Sector")
            result["TorqueFEMSector [N*m]"] = torque_sector
            result["TorqueVirtualFEM [N*m]"] = torque_virtual
            torque_scaling_error = abs(torque_virtual - SECTOR_SCALE * torque_sector)
        result.update({
            "FluxA [Wb]": phi_a, "FluxB [Wb]": phi_b, "FluxC [Wb]": phi_c,
            "FluxD [Wb]": phi_d, "FluxQ [Wb]": phi_q,
            "TorqueVirtualFEM [N*m]": torque_virtual,
            "TorqueController [N*m]": -torque_virtual,
            "TorquePhaseFlux [N*m]": torque_phase,
            "RawABCFluxPath": flux_path,
        })
        if MODE in ("r5", "r6", "r7", "r8"):
            result.update({
                "TorqueFEMSector [N*m]": torque_sector,
                "SectorToFullScale [count]": SECTOR_SCALE,
            })
        manifest_path = os.path.join(anchor_dir, "evidence_manifest.json")
        manifest = {
            "point": point, "project": expected_project_name,
            "project_path": expected_project_path,
            "source_project_sha256": SOURCE_PROJECT_SHA256,
            "points_sha256": POINTS_SHA256, "fixed_phase_currents_a": list(abc),
            "fixed_field_current_a": float(point["If [A]"]),
            "sector_scaling": {
                "sector_fraction": 1.0 / SECTOR_SCALE,
                "full_machine_scale": SECTOR_SCALE,
                "raw_sector_abc_flux_path": os.path.abspath(flux_path),
                "raw_abc_flux_wb": [raw_phi_a, raw_phi_b, raw_phi_c],
                "full_machine_abc_flux_wb": [phi_a, phi_b, phi_c],
                "raw_sector_coenergy_j": {
                    "m2": raw_w_m2, "m1": raw_w_m1,
                    "p1": raw_w_p1, "p2": raw_w_p2,
                },
                "full_machine_coenergy_j": {
                    "m2": w_m2, "m1": w_m1, "p1": w_p1, "p2": w_p2,
                },
                "torque_fem_sector_nm": torque_sector,
                "torque_fem_full_machine_nm": torque_virtual,
                "torque_sector_output": "Torque_FEM_Sector" if MODE in ("r5", "r6", "r7", "r8") else None,
                "torque_full_machine_output": TORQUE_OUTPUT_NAME,
                "torque_fem_is_already_scaled": MODE in ("r5", "r6", "r7", "r8"),
                "torque_scaling_identity_verified": (
                    MODE not in ("r5", "r6", "r7", "r8")
                    or torque_scaling_error <= 1e-8
                ),
            },
            "solve_order_mechanical_deg": list(OFFSETS),
            "solve_evidence": solve_evidence,
            "session_manifest_path": os.path.abspath(session_manifest_path),
            "session_manifest_sha256": sha256_file(session_manifest_path),
        }
        artifact_paths = [flux_path]
        for label in ("m2", "p2", "m1", "p1", "nominal"):
            evidence = solve_evidence[label]
            artifact_paths.extend([
                evidence["mesh_path"], evidence["convergence_path"],
                evidence["coenergy_path"],
            ])
        manifest["artifacts"] = [artifact_record(path) for path in artifact_paths]
        with open(manifest_path, "w") as stream:
            json.dump(normalize(manifest), stream, indent=2)
        result["EvidenceManifestPath"] = manifest_path
        if torque_scaling_error > 1e-8:
            raise RuntimeError(
                "Quarter-sector torque scaling identity failed: Torque_FEM != 4*Torque_FEM_Sector"
            )
        result["SolverMessages"] = json.dumps(dict(
            (label, evidence["messages"]) for label, evidence in solve_evidence.items()
        ), sort_keys=True)
        result["SolverStatus"] = "converged"
        payload["completed"].append(point["PointName"])
        payload.update({"status": "partial_resume_required", "stage": "restore"})
except BaseException as exc:
    payload.update({
        "status": "failed", "stage": "restore",
        "failure": {"error": str(exc), "traceback": traceback.format_exc().splitlines()},
    })
    if result is not None:
        result["SolverStatus"] = "failed"
        result["SolverMessages"] = json.dumps({"errors": [str(exc)]}, sort_keys=True)
finally:
    try:
        if "editor" in globals() and state.get("angle"):
            rotate(editor, -state["angle"])
            state["angle"] = 0.0
        if "design" in globals() and "originals" in globals():
            restore_parametric(design, originals)
        if "project" in globals():
            project.Save()
    except BaseException as exc:
        restoration_error = {"error": str(exc), "traceback": traceback.format_exc().splitlines()}
        payload["restoration_error"] = restoration_error
        payload["status"] = "error"
    if result is not None:
        if restoration_error:
            result["SolverStatus"] = "failed"
            result["SolverMessages"] = json.dumps({"errors": [restoration_error["error"]]}, sort_keys=True)
        append_result(result)
    if payload.get("status") == "partial_resume_required" and len(payload.get("completed", [])) == 10:
        payload["status"] = "complete"
    payload["active_point"] = None
    payload["stage"] = "idle"
    write_status(payload)
    try:
        AddWarningMessage("Task 9 corrected r3 anchor status: " + STATUS_PATH)
    except BaseException:
        print(STATUS_PATH)
