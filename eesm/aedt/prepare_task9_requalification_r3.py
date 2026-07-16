"""Freeze the corrected r3 ten-anchor Task 9 requalification campaign."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_ID = "eesm_task9_torque_requal_r3_20260716"
REVISION_ID = "eesm_requal_r3_gui_working_20260716_01"
ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r3_gui_recovery_20260716_01"
PROJECT = (
    REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
    / "eesm_requal_r3_gui_recovery_20260716_01"
    / "eesm_requal_r3_gui_working_20260716_01.aedt"
)
MODEL_STATUS = ROOT / "model_configuration_status.json"
MODEL_BUILD_STATUS = None
CRASH_DUMP = None
EXPECTED_MODEL_BUILD_STATUS_SHA256 = None
EXPECTED_MODEL_STATUS_SHA256 = None
EXPECTED_CRASH_DUMP_SHA256 = None
PROJECT_SHA256 = "e99d4aba12ac4dc139e8797482bb54c2240a1134d277ef74ee7fcb4f19aa57a9"
POINTS_PATH = ROOT / "frozen_points.csv"
FREEZE_PATH = ROOT / "requalification_freeze.json"
MODEL_AUDIT_PATH = ROOT / "qualification_model_audit.json"
MODE = os.environ.get("EESM_REQUAL_MODE", "r3")
if MODE == "r4":
    CAMPAIGN_ID = "eesm_task9_torque_requal_r4_20260716"
    REVISION_ID = "eesm_requal_direct_r4_04"
    ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r4_attempt4_20260716"
    PROJECT = (
        REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
        / "eesm_requal_direct_r4_04" / "eesm_requal_direct_r4_04.aedt"
    )
    MODEL_STATUS = (
        REPO_ROOT / "out" / "eesm" / "task9_requalification_r4"
        / "model_verification_attempt4.json"
    )
    PROJECT_SHA256 = "4ff65ae2c158679c8caa6ece2d38a86b931cf6d0e945ea745aaa6714e03236a7"
    POINTS_PATH = ROOT / "frozen_points.csv"
    FREEZE_PATH = ROOT / "requalification_freeze.json"
    MODEL_AUDIT_PATH = ROOT / "qualification_model_audit.json"
elif MODE == "r5":
    CAMPAIGN_ID = "eesm_task9_torque_requal_r5_20260716"
    REVISION_ID = "eesm_requal_direct_r5_01"
    ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r5_attempt1_20260716"
    PROJECT = (
        REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
        / "eesm_requal_direct_r5_01" / "eesm_requal_direct_r5_01.aedt"
    )
    MODEL_BUILD_STATUS = (
        REPO_ROOT / "out" / "eesm" / "task9_requalification_r5"
        / "model_build_status_attempt1.json"
    )
    MODEL_STATUS = (
        REPO_ROOT / "out" / "eesm" / "task9_requalification_r5"
        / "model_verification_attempt2.json"
    )
    PROJECT_SHA256 = "4fccd71493d0864db866ff0c55d01fe0e3fb304da76f5feb55ef3fe2ffabe830"
    POINTS_PATH = ROOT / "frozen_points.csv"
    FREEZE_PATH = ROOT / "requalification_freeze.json"
    MODEL_AUDIT_PATH = ROOT / "qualification_model_audit.json"
elif MODE == "r6":
    CAMPAIGN_ID = "eesm_task9_torque_requal_r6_20260716"
    REVISION_ID = "eesm_requal_direct_r6_01"
    ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r6_attempt1_20260716"
    PROJECT = (
        REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
        / "eesm_requal_direct_r6_01" / "eesm_requal_direct_r6_01.aedt"
    )
    MODEL_BUILD_STATUS = (
        REPO_ROOT / "out" / "eesm" / "task9_requalification_r6"
        / "model_build_status_attempt2.json"
    )
    MODEL_STATUS = (
        REPO_ROOT / "out" / "eesm" / "task9_requalification_r6"
        / "model_verification_attempt2.json"
    )
    PROJECT_SHA256 = "404a4b6f5a7e91f9c3bd69087c5a50e43ac51b22b899cbbb168e5e55feffbbcd"
    POINTS_PATH = ROOT / "frozen_points.csv"
    FREEZE_PATH = ROOT / "requalification_freeze.json"
    MODEL_AUDIT_PATH = ROOT / "qualification_model_audit.json"
elif MODE == "r7":
    CAMPAIGN_ID = "eesm_task9_torque_requal_r7_20260716"
    REVISION_ID = "eesm_requal_direct_r7_01"
    ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r7_attempt1_20260716"
    PROJECT = (
        REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
        / "eesm_requal_direct_r7_01" / "eesm_requal_direct_r7_01.aedt"
    )
    MODEL_BUILD_STATUS = (
        REPO_ROOT / "out" / "eesm" / "task9_requalification_r7"
        / "model_build_status_attempt1.json"
    )
    MODEL_STATUS = (
        REPO_ROOT / "out" / "eesm" / "task9_requalification_r7"
        / "model_verification_attempt1.json"
    )
    PROJECT_SHA256 = "527d2430823b981f6eff753d8044abc061029d12446c9b17196d16c3acd53bf1"
    POINTS_PATH = ROOT / "frozen_points.csv"
    FREEZE_PATH = ROOT / "requalification_freeze.json"
    MODEL_AUDIT_PATH = ROOT / "qualification_model_audit.json"
elif MODE == "r8":
    CAMPAIGN_ID = "eesm_task9_torque_requal_r8_20260716"
    REVISION_ID = "eesm_requal_direct_r8_01"
    ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r8_attempt1_20260716"
    PROJECT = (
        REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
        / "eesm_requal_direct_r8_01" / "eesm_requal_direct_r8_01.aedt"
    )
    MODEL_BUILD_STATUS = (
        REPO_ROOT / "out" / "eesm" / "task9_requalification_r8"
        / "model_build_status_attempt1.json"
    )
    MODEL_STATUS = (
        REPO_ROOT / "out" / "eesm" / "task9_requalification_r8"
        / "model_verification_attempt1.json"
    )
    CRASH_DUMP = (
        REPO_ROOT / "out" / "eesm" / "task9_requalification_r8"
        / "r8_verifier_ansysedtsv.dmp"
    )
    PROJECT_SHA256 = "28defa3863eb863de5b0a0deed826fc4a686116acd2c9d84804d93ef72cb0d98"
    EXPECTED_MODEL_BUILD_STATUS_SHA256 = "74ac19578532ddc883f1d46ab4c2acc0ca5cbee346f1e65d6078557b5d03cd64"
    EXPECTED_MODEL_STATUS_SHA256 = "7b471ea41b17bd8c93f747c17dd55b5123c0618bbe6fd600dc00d736dbbf1c44"
    EXPECTED_CRASH_DUMP_SHA256 = "9eb5b2afbbe90d44459305d3d00455a7bc1512d71aff1726f387fa1d81d2e062"
    POINTS_PATH = ROOT / "frozen_points.csv"
    FREEZE_PATH = ROOT / "requalification_freeze.json"
    MODEL_AUDIT_PATH = ROOT / "qualification_model_audit.json"
POINT_FIELDS = (
    "PointName", "point_id", "region", "Id [A]", "Iq [A]", "If [A]",
    "purpose", "campaign_id",
)
ANCHORS = (
    ("field_only", 0.0, 0.0, 2.0, "interior", "task8_field_only"),
    ("q_current", 0.0, 10.0, 2.0, "interior", "task8_q_current"),
    ("negative_d", -10.0, 0.0, 2.0, "field_weakening", "task8_negative_d"),
    ("combined_rated", -10.0, 10.0, 2.0, "boundary", "task8_combined_rated"),
    ("saturation_neighborhood", -20.0, 20.0, 3.0, "saturation", "task8_saturation"),
    ("q_sign_negative", 0.0, -10.0, 2.0, "interior", "task8_q_sign"),
    ("d_sign_positive", 10.0, 0.0, 2.0, "interior", "task8_d_sign"),
    ("task9_worst_boundary", -120.0, 120.0, 15.0, "boundary", "task9_worst_boundary"),
    ("field_weakening_anchor_1", -100.0, 30.0, 3.0, "field_weakening", "reviewed_fw_anchor"),
    ("field_weakening_anchor_2", -110.0, 80.0, 10.0, "field_weakening", "reviewed_fw_anchor"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def current(value: float) -> str:
    return f"{(round(float(value), 9) or 0.0):.9f}"


def point_id(values: tuple[float, float, float]) -> str:
    return hashlib.sha256("|".join(map(current, values)).encode("ascii")).hexdigest()[:16]


def rows() -> list[dict[str, str]]:
    result = []
    for name, id_a, iq_a, if_a, region, purpose in ANCHORS:
        values = (id_a, iq_a, if_a)
        result.append({
            "PointName": name,
            "point_id": point_id(values),
            "region": region,
            "Id [A]": current(id_a),
            "Iq [A]": current(iq_a),
            "If [A]": current(if_a),
            "purpose": purpose,
            "campaign_id": CAMPAIGN_ID,
        })
    return result


def render_points(items: list[dict[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=POINT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(items)
    return stream.getvalue().encode("ascii")


def freeze() -> dict[str, object]:
    required = ((PROJECT, MODEL_STATUS)
                + ((MODEL_BUILD_STATUS,) if MODEL_BUILD_STATUS else ())
                + ((CRASH_DUMP,) if CRASH_DUMP else ()))
    if not all(path.is_file() for path in required):
        raise FileNotFoundError("Corrected project or verified model status is missing")
    if sha256(PROJECT) != PROJECT_SHA256:
        raise RuntimeError("Corrected r3 project hash drifted; refusing freeze")
    status = json.loads(MODEL_STATUS.read_text(encoding="utf-8"))
    expected_status = "verified" if MODE in ("r4", "r5", "r6", "r7", "r8") else "configured"
    expected_hash = PROJECT_SHA256 if MODE in ("r4", "r5", "r6", "r7", "r8") else PROJECT_SHA256.upper()
    if status.get("status") != expected_status or status.get("project_sha256") != expected_hash:
        raise RuntimeError("Corrected model verification is not green")
    build_status = None
    if MODE in ("r5", "r6", "r7", "r8"):
        build_status = json.loads(MODEL_BUILD_STATUS.read_text(encoding="utf-8"))
        expected_design = f"EESM_2D_Direct_{MODE.upper()}_Quarter"
        if (build_status.get("status") != "built"
                or build_status.get("project_sha256") != PROJECT_SHA256
                or build_status.get("design") != expected_design
                or build_status.get("maxwell_solve_attempted") is not False
                or status.get("design") != expected_design
                or status.get("maxwell_solve_attempted") is not False):
            raise RuntimeError(f"Direct {MODE} build/verification evidence is not green")
    if MODE == "r8":
        if (sha256(MODEL_BUILD_STATUS) != EXPECTED_MODEL_BUILD_STATUS_SHA256
                or sha256(MODEL_STATUS) != EXPECTED_MODEL_STATUS_SHA256
                or sha256(CRASH_DUMP) != EXPECTED_CRASH_DUMP_SHA256):
            raise RuntimeError("Direct r8 immutable build, verification, or crash evidence drifted")

    project_text = PROJECT.read_text(encoding="latin-1")
    if MODE in ("r5", "r6", "r7", "r8"):
        checks = {
            "model_depth_120mm": "ModelDepth='120mm'" in project_text,
            "four_windings_parallel_branches_1": project_text.count("ParallelBranchesNum='1'") >= 4,
            "two_field_terminals_80_turns": project_text.count("'Conductor number'='80'") >= 2,
            "quarter_periodic_boundaries": all(
                marker in project_text for marker in ("Quarter_Independent", "Quarter_Dependent")
            ),
            "sector_and_full_torque_outputs": (
                "Torque_FEM_Sector" in project_text and "4*TorqueRotor.Torque" in project_text
            ),
            "quarter_sector_objects": all(
                marker in project_text for marker in ("PoleAssembly_01", "Field_P01_NegT", "Field_P01_PosT")
            ),
        }
        if MODE in ("r7", "r8"):
            checks.update({
                "rmxprt_outer_region": (
                    "DllName='RMxprt/Band'" in project_text
                    and "Name='OuterRegion'" in project_text
                ),
                "single_shared_tool_topology": (
                    "Name='InfoCore'" in project_text
                    and "RegionParameters" not in project_text
                    and "_QuadrantClip" not in project_text
                ),
            })
    elif MODE == "r4":
        checks = {
            "model_depth_120mm": "ModelDepth='120mm'" in project_text,
            "four_windings_parallel_branches_1": project_text.count("ParallelBranchesNum='1'") >= 4,
            "eight_field_terminals_80_turns": project_text.count("'Conductor number'='80'") >= 8,
            "no_damper_or_symmetry_objects": all(
                marker not in project_text for marker in ("EndConnection1", "Name='Band'", "Name='InnerRegion'")
            ),
            "direct_full_model_region": "Name='Region'" in project_text and "Outer_A0" in project_text,
            "torque_parameter_and_output": "TorqueRotor" in project_text and "Torque_FEM" in project_text,
        }
    else:
        checks = {
            "model_depth_120mm": "ModelDepth='120mm'" in project_text,
            "three_phase_parallel_branches_4": project_text.count("ParallelBranchesNum='4'") >= 3,
            "field_parallel_branches_1": "ParallelBranchesNum='1'" in project_text,
            "two_field_coils_80_turns": project_text.count("'Conductor number'='80'") >= 2,
            "no_active_damper_end_connection": "EndConnection1" not in project_text,
            "temporary_bar_regions_are_steel_fill": project_text.count("MaterialValue='\"steel_1008\"'") >= 3,
            "torque_parameter_and_output": "TorqueRotor" in project_text and "Torque_FEM" in project_text,
        }
    if not all(checks.values()):
        raise RuntimeError("Corrected r3 project failed offline model audit: " + str(checks))
    audit = {
        "status": "pass",
        "project": PROJECT.relative_to(REPO_ROOT).as_posix(),
        "project_sha256": PROJECT_SHA256,
        "checks": {name: {"status": "pass"} for name in checks},
        "solve_attempted": False,
    }

    point_rows = rows()
    if len(point_rows) != 10 or len({row["point_id"] for row in point_rows}) != 10:
        raise RuntimeError("Invalid ten-anchor budget or identity")
    points_bytes = render_points(point_rows)
    freeze_payload = {
        "campaign_id": CAMPAIGN_ID,
        "revision_id": REVISION_ID,
        "project_sha256": PROJECT_SHA256,
        "model_status_sha256": sha256(MODEL_STATUS),
        "anchors_sha256": hashlib.sha256(points_bytes).hexdigest(),
        "budget": 10,
        "max_new_anchors_per_session": 1,
        "torque_tolerance_nm": 1.1,
        "coenergy_angle_offsets_mechanical_deg": [-2.0, -1.0, 1.0, 2.0],
        "acceptance_frozen_before_solve": True,
        "new_task9_campaign_authorized": False,
        "task_10_authorized": False,
    }
    if MODEL_BUILD_STATUS:
        freeze_payload["model_build_status_sha256"] = sha256(MODEL_BUILD_STATUS)
    if CRASH_DUMP:
        freeze_payload["post_verification_crash_evidence"] = {
            "path": CRASH_DUMP.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256(CRASH_DUMP),
            "note": "AEDT crashed after the verifier wrote green no-solve evidence; the dump is preserved and does not authorize qualification.",
        }

    targets = (POINTS_PATH, FREEZE_PATH, MODEL_AUDIT_PATH)
    if any(path.exists() for path in targets):
        if not all(path.is_file() for path in targets):
            raise FileExistsError("Incomplete r3 freeze; refusing overwrite")
        if POINTS_PATH.read_bytes() != points_bytes:
            raise FileExistsError("Frozen r3 anchor bytes differ")
        if json.loads(FREEZE_PATH.read_text(encoding="utf-8")) != freeze_payload:
            raise FileExistsError("Frozen r3 contract differs")
        if json.loads(MODEL_AUDIT_PATH.read_text(encoding="utf-8")) != audit:
            raise FileExistsError("Frozen r3 model audit differs")
        return freeze_payload

    ROOT.mkdir(parents=True, exist_ok=True)
    POINTS_PATH.write_bytes(points_bytes)
    MODEL_AUDIT_PATH.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    FREEZE_PATH.write_text(json.dumps(freeze_payload, indent=2), encoding="utf-8")
    return freeze_payload


if __name__ == "__main__":
    print(json.dumps(freeze(), indent=2))
