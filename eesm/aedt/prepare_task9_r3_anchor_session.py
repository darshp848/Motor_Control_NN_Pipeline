"""Create the next write-once per-anchor AEDT project copy for r3 qualification."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r3_gui_recovery_20260716_01"
POINTS = CAMPAIGN_ROOT / "frozen_points.csv"
PROGRESS = CAMPAIGN_ROOT / "raw" / "diagnostic_progress.csv"
SOURCE = (
    REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
    / "eesm_requal_r3_gui_recovery_20260716_01"
    / "eesm_requal_r3_gui_working_20260716_01.aedt"
)
SESSIONS_ROOT = REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects" / "task9_r3_sessions"
MANIFEST_ROOT = CAMPAIGN_ROOT / "raw" / "session_manifests"
SOURCE_SHA256 = "e99d4aba12ac4dc139e8797482bb54c2240a1134d277ef74ee7fcb4f19aa57a9"
POINTS_SHA256 = "9fec334340f777d57db639fbd2570d92ecfafa0f0bfaa1a37e0873868a9c057b"
CAMPAIGN_ID = "eesm_task9_torque_requal_r3_20260716"
PROJECT_PREFIX = "eesm_requal_r3_anchor_"
DESIGN_NAME = "EESM_2D_Qual"
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
MODE = os.environ.get("EESM_REQUAL_MODE", "r3")
if MODE == "r4":
    CAMPAIGN_ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r4_attempt4_20260716"
    POINTS = CAMPAIGN_ROOT / "frozen_points.csv"
    PROGRESS = CAMPAIGN_ROOT / "raw" / "diagnostic_progress.csv"
    SOURCE = (
        REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
        / "eesm_requal_direct_r4_04" / "eesm_requal_direct_r4_04.aedt"
    )
    SESSIONS_ROOT = REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects" / "task9_r4_sessions"
    MANIFEST_ROOT = CAMPAIGN_ROOT / "raw" / "session_manifests"
    SOURCE_SHA256 = "4ff65ae2c158679c8caa6ece2d38a86b931cf6d0e945ea745aaa6714e03236a7"
    POINTS_SHA256 = "5bb921f6304fcb35fee992ce3801a9c4ddad1b7aac696ba4d5740b183f962e38"
    CAMPAIGN_ID = "eesm_task9_torque_requal_r4_20260716"
    PROJECT_PREFIX = "eesm_requal_r4_anchor_"
    DESIGN_NAME = "EESM_2D_Direct_R4"
elif MODE == "r5":
    CAMPAIGN_ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r5_attempt1_20260716"
    POINTS = CAMPAIGN_ROOT / "frozen_points.csv"
    PROGRESS = CAMPAIGN_ROOT / "raw" / "diagnostic_progress.csv"
    SOURCE = (
        REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
        / "eesm_requal_direct_r5_01" / "eesm_requal_direct_r5_01.aedt"
    )
    SESSIONS_ROOT = REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects" / "task9_r5_sessions"
    MANIFEST_ROOT = CAMPAIGN_ROOT / "raw" / "session_manifests"
    SOURCE_SHA256 = "4fccd71493d0864db866ff0c55d01fe0e3fb304da76f5feb55ef3fe2ffabe830"
    POINTS_SHA256 = "92d5f79029679022f9a9b06490040c7332608643cd1657c945141db0928eb7d7"
    CAMPAIGN_ID = "eesm_task9_torque_requal_r5_20260716"
    PROJECT_PREFIX = "eesm_requal_r5_anchor_"
    DESIGN_NAME = "EESM_2D_Direct_R5_Quarter"
elif MODE == "r6":
    CAMPAIGN_ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r6_attempt1_20260716"
    POINTS = CAMPAIGN_ROOT / "frozen_points.csv"
    PROGRESS = CAMPAIGN_ROOT / "raw" / "diagnostic_progress.csv"
    SOURCE = (
        REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
        / "eesm_requal_direct_r6_01" / "eesm_requal_direct_r6_01.aedt"
    )
    SESSIONS_ROOT = REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects" / "task9_r6_sessions"
    MANIFEST_ROOT = CAMPAIGN_ROOT / "raw" / "session_manifests"
    SOURCE_SHA256 = "404a4b6f5a7e91f9c3bd69087c5a50e43ac51b22b899cbbb168e5e55feffbbcd"
    POINTS_SHA256 = "de5374112705f8274ab3fbf276fc692efe404928333c1bac0b9883db1db16ad2"
    CAMPAIGN_ID = "eesm_task9_torque_requal_r6_20260716"
    PROJECT_PREFIX = "eesm_requal_r6_anchor_"
    DESIGN_NAME = "EESM_2D_Direct_R6_Quarter"
elif MODE == "r7":
    CAMPAIGN_ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r7_attempt1_20260716"
    POINTS = CAMPAIGN_ROOT / "frozen_points.csv"
    PROGRESS = CAMPAIGN_ROOT / "raw" / "diagnostic_progress.csv"
    SOURCE = (
        REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
        / "eesm_requal_direct_r7_01" / "eesm_requal_direct_r7_01.aedt"
    )
    SESSIONS_ROOT = REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects" / "task9_r7_sessions"
    MANIFEST_ROOT = CAMPAIGN_ROOT / "raw" / "session_manifests"
    SOURCE_SHA256 = "527d2430823b981f6eff753d8044abc061029d12446c9b17196d16c3acd53bf1"
    POINTS_SHA256 = "43b87920ab04d8f9aa371a739a2d0dc4c3464789a4d702442df60d6a1488e7b1"
    CAMPAIGN_ID = "eesm_task9_torque_requal_r7_20260716"
    PROJECT_PREFIX = "eesm_requal_r7_anchor_"
    DESIGN_NAME = "EESM_2D_Direct_R7_Quarter"
elif MODE == "r8":
    CAMPAIGN_ROOT = REPO_ROOT / "out" / "eesm" / "task9_requalification_r8_attempt1_20260716"
    POINTS = CAMPAIGN_ROOT / "frozen_points.csv"
    PROGRESS = CAMPAIGN_ROOT / "raw" / "diagnostic_progress.csv"
    SOURCE = (
        REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects"
        / "eesm_requal_direct_r8_01" / "eesm_requal_direct_r8_01.aedt"
    )
    SESSIONS_ROOT = REPO_ROOT / "aedt_mcp" / "tmp" / "aedt_projects" / "task9_r8_sessions"
    MANIFEST_ROOT = CAMPAIGN_ROOT / "raw" / "session_manifests"
    SOURCE_SHA256 = "28defa3863eb863de5b0a0deed826fc4a686116acd2c9d84804d93ef72cb0d98"
    POINTS_SHA256 = "b7f8a469ab3fc7472fea3ef2eac7fdf9140f9488c884aa978d8e7409efbca77b"
    CAMPAIGN_ID = "eesm_task9_torque_requal_r8_20260716"
    PROJECT_PREFIX = "eesm_requal_r8_anchor_"
    DESIGN_NAME = "EESM_2D_Direct_R8_Quarter"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare() -> dict[str, object]:
    freeze_path = CAMPAIGN_ROOT / "requalification_freeze.json"
    if not freeze_path.is_file():
        raise RuntimeError("Qualification campaign must be frozen before preparing a session")
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    if (frozen.get("campaign_id") != CAMPAIGN_ID
            or frozen.get("project_sha256") != SOURCE_SHA256
            or frozen.get("anchors_sha256") != POINTS_SHA256
            or frozen.get("acceptance_frozen_before_solve") is not True
            or frozen.get("new_task9_campaign_authorized") is not False
            or frozen.get("task_10_authorized") is not False):
        raise RuntimeError("Frozen qualification contract drifted")
    if MODE == "r8" and (
            frozen.get("model_build_status_sha256") !=
            "74ac19578532ddc883f1d46ab4c2acc0ca5cbee346f1e65d6078557b5d03cd64"
            or frozen.get("model_status_sha256") !=
            "7b471ea41b17bd8c93f747c17dd55b5123c0618bbe6fd600dc00d736dbbf1c44"
            or frozen.get("post_verification_crash_evidence", {}).get("sha256") !=
            "9eb5b2afbbe90d44459305d3d00455a7bc1512d71aff1726f387fa1d81d2e062"):
        raise RuntimeError("Frozen r8 build, verification, or crash evidence binding drifted")
    if sha256(SOURCE) != SOURCE_SHA256 or sha256(POINTS) != POINTS_SHA256:
        raise RuntimeError("Verified r3 source or frozen anchor hash drifted")
    with POINTS.open(newline="", encoding="ascii") as stream:
        points = list(csv.DictReader(stream))
    if len(points) != 10 or any(point["campaign_id"] != CAMPAIGN_ID for point in points):
        raise RuntimeError("Invalid frozen r3 anchor campaign")
    expected = {point["point_id"]: point for point in points}
    completed: set[str] = set()
    if PROGRESS.is_file():
        with PROGRESS.open(newline="", encoding="ascii") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != FIELDS:
                raise RuntimeError("Malformed r3 progress header")
            rows = list(reader)
        for row in rows:
            point_id = row.get("PointID", "")
            if point_id not in expected or point_id in completed:
                raise RuntimeError("Unknown or duplicate prior r3 point")
            point = expected[point_id]
            if (row.get("SolverStatus") != "converged"
                    or row.get("PointName") != point["PointName"]
                    or row.get("Region") != point["region"]
                    or row.get("Purpose") != point["purpose"]
                    or any(float(row[key]) != float(point[key])
                           for key in ("Id [A]", "Iq [A]", "If [A]"))
                    or row.get("Project") != PROJECT_PREFIX + point["PointName"]
                    or row.get("Design") != DESIGN_NAME
                    or row.get("Setup") != "Setup_Qual"
                    or row.get("SourceProjectSHA256") != SOURCE_SHA256
                    or row.get("PointsSHA256") != POINTS_SHA256):
                raise RuntimeError("Prior anchor row drifted; operator review required")
            for key in ("RawABCFluxPath", "EvidenceManifestPath"):
                evidence = Path(row.get(key, ""))
                if not evidence.is_file() or evidence.stat().st_size <= 0:
                    raise RuntimeError("Prior anchor evidence is missing")
            completed.add(point_id)
    remaining = [point for point in points if point["point_id"] not in completed]
    if not remaining:
        return {"status": "complete", "completed": len(completed)}

    point = remaining[0]
    project_name = PROJECT_PREFIX + point["PointName"]
    target_dir = SESSIONS_ROOT / project_name
    target = target_dir / (project_name + ".aedt")
    manifest = MANIFEST_ROOT / (point["PointName"] + ".json")
    if target_dir.exists() or manifest.exists():
        raise FileExistsError("Anchor session already exists; refusing overwrite: " + point["PointName"])

    target_dir.mkdir(parents=True)
    shutil.copy2(SOURCE, target)
    if sha256(target) != SOURCE_SHA256:
        raise RuntimeError("Anchor project copy hash mismatch")
    payload = {
        "status": "prepared",
        "point": point,
        "project_name": project_name,
        "project_path": str(target),
        "source_project": str(SOURCE),
        "source_project_sha256": SOURCE_SHA256,
        "points_sha256": POINTS_SHA256,
        "completed_before_session": len(completed),
    }
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
