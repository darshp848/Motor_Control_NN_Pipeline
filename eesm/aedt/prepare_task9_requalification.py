"""Freeze the write-once Task 9 torque requalification diagnostic."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUALIFICATION_ID = "eesm_task9_torque_requal_r2_20260716"
REVISION_ID = "eesm_requal_r2"
REQUALIFICATION_ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r2"
ORIGINAL_TASK9_ROOT = REPO_ROOT / "out" / "eesm" / "task9_baseline"
SOURCE_PROJECT = REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects" / "eesm_qual" / "eesm_qual.aedt"
SOURCE_PROJECT_SHA256 = "28aedc7f1d55832d2239660638b0b2f91d0839367b836994d70d0e0fa1f386cc"
ORIGINAL_TASK9_POINTS_SHA256 = "3ce7f7bd4bc2abbe7aefb425d2923fa488286603c32ec506d20eecbbc361fb6d"
POINTS_PATH = REQUALIFICATION_ROOT / "frozen_points.csv"
FREEZE_PATH = REQUALIFICATION_ROOT / "requalification_freeze.json"
SNAPSHOT_PATH = REQUALIFICATION_ROOT / "original_task9_snapshot.json"
MODEL_AUDIT_PATH = REQUALIFICATION_ROOT / "model_contract_audit.json"
REQUALIFICATION_BUDGET = 10
FIELDS = ("PointName", "point_id", "region", "Id [A]", "Iq [A]", "If [A]", "purpose", "campaign_id")

# Frozen from the seven Task 8 probes plus the declared worst-boundary and two
# reviewed field-weakening anchors. The list is not selected from fitted data.
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _format_current(value: float) -> str:
    return f"{(round(float(value), 9) or 0.0):.9f}"


def _point_id(values: tuple[float, float, float]) -> str:
    payload = "|".join(_format_current(value) for value in values)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()[:16]


def build_rows() -> list[dict[str, str]]:
    rows = []
    for name, id_a, iq_a, if_a, region, purpose in ANCHORS:
        values = (id_a, iq_a, if_a)
        rows.append({
            "PointName": name,
            "point_id": _point_id(values),
            "region": region,
            "Id [A]": _format_current(id_a),
            "Iq [A]": _format_current(iq_a),
            "If [A]": _format_current(if_a),
            "purpose": purpose,
            "campaign_id": REQUALIFICATION_ID,
        })
    return rows


def _render(rows: list[dict[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("ascii")


def _inventory(root: Path) -> list[dict[str, object]]:
    return [
        {"path": path.relative_to(REPO_ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": _sha256(path)}
        for path in sorted(root.rglob("*")) if path.is_file()
    ]


def freeze_requalification() -> dict[str, object]:
    required = (
        ORIGINAL_TASK9_ROOT / "frozen_points.csv",
        ORIGINAL_TASK9_ROOT / "campaign_freeze.json",
        ORIGINAL_TASK9_ROOT / "canonical_campaign.csv",
        ORIGINAL_TASK9_ROOT / "campaign_report.json",
        SOURCE_PROJECT,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing preservation input: " + ", ".join(missing))
    if _sha256(required[0]) != ORIGINAL_TASK9_POINTS_SHA256:
        raise RuntimeError("Original Task 9 point hash drifted; refusing requalification")
    if _sha256(SOURCE_PROJECT) != SOURCE_PROJECT_SHA256:
        raise RuntimeError("Source AEDT project hash drifted; refusing requalification")

    rows = build_rows()
    if len(rows) != REQUALIFICATION_BUDGET or len({row["point_id"] for row in rows}) != len(rows):
        raise RuntimeError("Invalid requalification point budget or identity")
    points_bytes = _render(rows)
    anchors_sha256 = hashlib.sha256(points_bytes).hexdigest()
    project_text = SOURCE_PROJECT.read_text(encoding="latin-1")
    model_audit = {
        "status": "fail",
        "source_project_sha256": SOURCE_PROJECT_SHA256,
        "checks": {
            "model_depth_120mm": {
                "status": "pass" if "ModelDepth='120mm'" in project_text else "fail",
                "observed": "77.0793mm" if "ModelDepth='77.0793mm'" in project_text else "unknown",
                "required": "120mm",
            },
            "field_turns_80_per_pole": {
                "status": "pass" if "ConductorsPerPole='160'" in project_text else "fail",
                "observed": "40" if "ConductorsPerPole='40'" in project_text else "unknown",
                "required": "160 active conductors = 80 series turns per pole",
            },
            "no_damper_cage": {
                "status": "fail" if "Bar_Separate1" in project_text or "Bar_Separate2" in project_text else "pass",
                "observed": "Bar, Bar_Separate1, Bar_Separate2" if "Bar_Separate1" in project_text else "none",
                "required": "no damper cage",
            },
        },
        "decision": "do_not_solve_build_new_compliant_revision",
    }
    if all(item["status"] == "pass" for item in model_audit["checks"].values()):
        model_audit["status"] = "pass"
    snapshot = {
        "policy": "source_project_copy_only_no_overwrite",
        "original_task9_snapshot": _inventory(ORIGINAL_TASK9_ROOT),
        "source_project": SOURCE_PROJECT.relative_to(REPO_ROOT).as_posix(),
        "source_project_sha256": SOURCE_PROJECT_SHA256,
    }
    freeze = {
        "requalification_id": REQUALIFICATION_ID,
        "revision_id": REVISION_ID,
        "budget": REQUALIFICATION_BUDGET,
        "anchors_sha256": anchors_sha256,
        "source_project_sha256": SOURCE_PROJECT_SHA256,
        "original_task9_points_sha256": ORIGINAL_TASK9_POINTS_SHA256,
        "torque_tolerance_nm": 1.1,
        "coenergy_angle_offsets_mechanical_deg": [-2.0, -1.0, 1.0, 2.0],
        "acceptance_frozen_before_solve": True,
        "task_10_authorized": False,
    }
    globals()["ANCHORS_SHA256"] = anchors_sha256

    if any(path.exists() for path in (POINTS_PATH, FREEZE_PATH, SNAPSHOT_PATH, MODEL_AUDIT_PATH)):
        if not all(path.is_file() for path in (POINTS_PATH, FREEZE_PATH, SNAPSHOT_PATH, MODEL_AUDIT_PATH)):
            raise FileExistsError("Incomplete requalification freeze; refusing overwrite")
        if POINTS_PATH.read_bytes() != points_bytes:
            raise FileExistsError("Frozen requalification points differ; refusing overwrite")
        if json.loads(FREEZE_PATH.read_text(encoding="utf-8")) != freeze:
            raise FileExistsError("Frozen requalification contract differs; refusing overwrite")
        if json.loads(MODEL_AUDIT_PATH.read_text(encoding="utf-8")) != model_audit:
            raise FileExistsError("Frozen model audit differs; refusing overwrite")
        return freeze

    REQUALIFICATION_ROOT.mkdir(parents=True, exist_ok=True)
    POINTS_PATH.write_bytes(points_bytes)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    MODEL_AUDIT_PATH.write_text(json.dumps(model_audit, indent=2), encoding="utf-8")
    FREEZE_PATH.write_text(json.dumps(freeze, indent=2), encoding="utf-8")
    return freeze


if __name__ == "__main__":
    print(json.dumps(freeze_requalification(), indent=2))
