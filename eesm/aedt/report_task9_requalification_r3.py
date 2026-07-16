"""Independently recompute and gate the corrected-r3 ten-anchor evidence."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path


TOLERANCE_NM = 1.1
IDENTITY_TOLERANCE = 1e-8
POLE_PAIRS = 2
THETA = math.pi
SOURCE_PROJECT_SHA256 = "e99d4aba12ac4dc139e8797482bb54c2240a1134d277ef74ee7fcb4f19aa57a9"
POINTS_SHA256 = "9fec334340f777d57db639fbd2570d92ecfafa0f0bfaa1a37e0873868a9c057b"
CAMPAIGN_ID = "eesm_task9_torque_requal_r3_20260716"
PROJECT_PREFIX = "eesm_requal_r3_anchor_"
DESIGN_NAME = "EESM_2D_Qual"
SECTOR_SCALE = 1.0
SOLVE_LABELS = ("m2", "p2", "m1", "p1", "nominal")
DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "out" / "eesm" / "task9_requalification_r3_gui_recovery_20260716_01"
MODE = os.environ.get("EESM_REQUAL_MODE", "r3")
if MODE == "r4":
    SOURCE_PROJECT_SHA256 = "4ff65ae2c158679c8caa6ece2d38a86b931cf6d0e945ea745aaa6714e03236a7"
    POINTS_SHA256 = "5bb921f6304fcb35fee992ce3801a9c4ddad1b7aac696ba4d5740b183f962e38"
    CAMPAIGN_ID = "eesm_task9_torque_requal_r4_20260716"
    PROJECT_PREFIX = "eesm_requal_r4_anchor_"
    DESIGN_NAME = "EESM_2D_Direct_R4"
    DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "out" / "eesm" / "task9_requalification_r4_attempt4_20260716"
elif MODE == "r5":
    DEFAULT_ROOT = Path(os.environ.get(
        "EESM_R5_CAMPAIGN_ROOT",
        Path(__file__).resolve().parents[2] / "out" / "eesm" / "task9_requalification_r5_20260716",
    )).resolve()
    freeze_path = DEFAULT_ROOT / "requalification_freeze.json"
    if not freeze_path.is_file():
        raise RuntimeError("R5 qualification must be frozen before reporting")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    SOURCE_PROJECT_SHA256 = "4fccd71493d0864db866ff0c55d01fe0e3fb304da76f5feb55ef3fe2ffabe830"
    POINTS_SHA256 = str(freeze.get("anchors_sha256", ""))
    CAMPAIGN_ID = str(freeze.get("campaign_id", ""))
    if (len(POINTS_SHA256) != 64 or not CAMPAIGN_ID
            or freeze.get("project_sha256") != SOURCE_PROJECT_SHA256):
        raise RuntimeError("Frozen r5 qualification metadata is incomplete or source-bound incorrectly")
    PROJECT_PREFIX = "eesm_requal_r5_anchor_"
    DESIGN_NAME = "EESM_2D_Direct_R5_Quarter"
    SECTOR_SCALE = 4.0
elif MODE == "r6":
    DEFAULT_ROOT = Path(os.environ.get(
        "EESM_R6_CAMPAIGN_ROOT",
        Path(__file__).resolve().parents[2] / "out" / "eesm" / "task9_requalification_r6_attempt1_20260716",
    )).resolve()
    freeze_path = DEFAULT_ROOT / "requalification_freeze.json"
    if not freeze_path.is_file():
        raise RuntimeError("R6 qualification must be frozen before reporting")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    SOURCE_PROJECT_SHA256 = "404a4b6f5a7e91f9c3bd69087c5a50e43ac51b22b899cbbb168e5e55feffbbcd"
    POINTS_SHA256 = str(freeze.get("anchors_sha256", ""))
    CAMPAIGN_ID = str(freeze.get("campaign_id", ""))
    if (len(POINTS_SHA256) != 64 or not CAMPAIGN_ID
            or freeze.get("project_sha256") != SOURCE_PROJECT_SHA256):
        raise RuntimeError("Frozen r6 qualification metadata is incomplete or source-bound incorrectly")
    PROJECT_PREFIX = "eesm_requal_r6_anchor_"
    DESIGN_NAME = "EESM_2D_Direct_R6_Quarter"
    SECTOR_SCALE = 4.0
elif MODE == "r7":
    DEFAULT_ROOT = Path(os.environ.get(
        "EESM_R7_CAMPAIGN_ROOT",
        Path(__file__).resolve().parents[2] / "out" / "eesm" / "task9_requalification_r7_attempt1_20260716",
    )).resolve()
    freeze_path = DEFAULT_ROOT / "requalification_freeze.json"
    if not freeze_path.is_file():
        raise RuntimeError("R7 qualification must be frozen before reporting")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    SOURCE_PROJECT_SHA256 = "527d2430823b981f6eff753d8044abc061029d12446c9b17196d16c3acd53bf1"
    POINTS_SHA256 = str(freeze.get("anchors_sha256", ""))
    CAMPAIGN_ID = str(freeze.get("campaign_id", ""))
    if (len(POINTS_SHA256) != 64 or not CAMPAIGN_ID
            or freeze.get("project_sha256") != SOURCE_PROJECT_SHA256):
        raise RuntimeError("Frozen r7 qualification metadata is incomplete or source-bound incorrectly")
    PROJECT_PREFIX = "eesm_requal_r7_anchor_"
    DESIGN_NAME = "EESM_2D_Direct_R7_Quarter"
    SECTOR_SCALE = 4.0
elif MODE == "r8":
    DEFAULT_ROOT = Path(os.environ.get(
        "EESM_R8_CAMPAIGN_ROOT",
        Path(__file__).resolve().parents[2] / "out" / "eesm" / "task9_requalification_r8_attempt1_20260716",
    )).resolve()
    freeze_path = DEFAULT_ROOT / "requalification_freeze.json"
    if not freeze_path.is_file():
        raise RuntimeError("R8 qualification must be frozen before reporting")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    SOURCE_PROJECT_SHA256 = "28defa3863eb863de5b0a0deed826fc4a686116acd2c9d84804d93ef72cb0d98"
    POINTS_SHA256 = str(freeze.get("anchors_sha256", ""))
    CAMPAIGN_ID = str(freeze.get("campaign_id", ""))
    if (len(POINTS_SHA256) != 64 or not CAMPAIGN_ID
            or freeze.get("project_sha256") != SOURCE_PROJECT_SHA256
            or freeze.get("model_build_status_sha256") !=
            "74ac19578532ddc883f1d46ab4c2acc0ca5cbee346f1e65d6078557b5d03cd64"
            or freeze.get("model_status_sha256") !=
            "7b471ea41b17bd8c93f747c17dd55b5123c0618bbe6fd600dc00d736dbbf1c44"
            or freeze.get("post_verification_crash_evidence", {}).get("sha256") !=
            "9eb5b2afbbe90d44459305d3d00455a7bc1512d71aff1726f387fa1d81d2e062"):
        raise RuntimeError("Frozen r8 qualification metadata is incomplete or source-bound incorrectly")
    PROJECT_PREFIX = "eesm_requal_r8_anchor_"
    DESIGN_NAME = "EESM_2D_Direct_R8_Quarter"
    SECTOR_SCALE = 4.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def evidence_manifest_ok(row: dict[str, str], point: dict[str, str]) -> bool:
    manifest_path = Path(row["EvidenceManifestPath"]).resolve()
    flux_path = Path(row["RawABCFluxPath"]).resolve()
    if not manifest_path.is_file() or manifest_path.stat().st_size <= 0:
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        anchor_dir = manifest_path.parent.resolve()
        expected_project = PROJECT_PREFIX + point["PointName"]
        if (manifest.get("point") != point
                or manifest.get("project") != expected_project
                or manifest.get("source_project_sha256") != SOURCE_PROJECT_SHA256
                or manifest.get("points_sha256") != POINTS_SHA256
                or manifest.get("solve_order_mechanical_deg") != [-2.0, 2.0, -1.0, 1.0, 0.0]
                or set(manifest.get("solve_evidence", {})) != set(SOLVE_LABELS)):
            return False
        session_manifest = Path(manifest["session_manifest_path"]).resolve()
        if (not session_manifest.is_file()
                or sha256(session_manifest) != manifest.get("session_manifest_sha256")):
            return False
        expected_paths = {flux_path}
        for label in SOLVE_LABELS:
            solve = manifest["solve_evidence"][label]
            if solve.get("messages", {}).get("errors"):
                return False
            expected_paths.update(Path(solve[key]).resolve() for key in (
                "mesh_path", "convergence_path", "coenergy_path"
            ))
        records = manifest.get("artifacts", [])
        if len(records) != 16:
            return False
        recorded_paths = {Path(record["path"]).resolve() for record in records}
        if recorded_paths != expected_paths:
            return False
        for record in records:
            path = Path(record["path"]).resolve()
            if (anchor_dir not in path.parents or not path.is_file()
                    or path.stat().st_size != record.get("size_bytes")
                    or sha256(path) != record.get("sha256")):
                return False
        if MODE in ("r5", "r6", "r7", "r8"):
            scaling = manifest.get("sector_scaling", {})
            if (scaling.get("sector_fraction") != 0.25
                    or scaling.get("full_machine_scale") != 4.0
                    or Path(scaling.get("raw_sector_abc_flux_path", "")).resolve() != flux_path
                    or scaling.get("torque_sector_output") != "Torque_FEM_Sector"
                    or scaling.get("torque_full_machine_output") != "Torque_FEM"
                    or scaling.get("torque_fem_is_already_scaled") is not True
                    or scaling.get("torque_scaling_identity_verified") is not True):
                return False
            raw_flux = [float(row[key]) for key in (
                "RawSectorFluxA [Wb]", "RawSectorFluxB [Wb]", "RawSectorFluxC [Wb]"
            )]
            full_flux = [float(row[key]) for key in (
                "FluxA [Wb]", "FluxB [Wb]", "FluxC [Wb]"
            )]
            manifest_raw_flux = scaling.get("raw_abc_flux_wb", [])
            manifest_full_flux = scaling.get("full_machine_abc_flux_wb", [])
            with flux_path.open(newline="", encoding="utf-8") as stream:
                flux_rows = list(csv.reader(stream))
            if len(flux_rows) < 2 or len(flux_rows[-1]) < 4:
                return False
            artifact_raw_flux = [float(value) for value in flux_rows[-1][1:4]]
            if (len(manifest_raw_flux) != 3 or len(manifest_full_flux) != 3
                    or any(abs(value - expected) > IDENTITY_TOLERANCE
                           for value, expected in zip(artifact_raw_flux, raw_flux))
                    or any(abs(float(value) - expected) > IDENTITY_TOLERANCE
                    for value, expected in zip(manifest_raw_flux, raw_flux))
                    or any(abs(value - expected) > IDENTITY_TOLERANCE
                           for value, expected in zip(
                               (float(value) for value in manifest_full_flux), full_flux
                           ))):
                return False
            raw_coenergy_keys = {
                "m2": "RawSectorCoenergyM2 [J]", "m1": "RawSectorCoenergyM1 [J]",
                "p1": "RawSectorCoenergyP1 [J]", "p2": "RawSectorCoenergyP2 [J]",
            }
            full_coenergy_keys = {
                "m2": "CoenergyM2 [J]", "m1": "CoenergyM1 [J]",
                "p1": "CoenergyP1 [J]", "p2": "CoenergyP2 [J]",
            }
            for label in ("m2", "m1", "p1", "p2"):
                raw_value = float(row[raw_coenergy_keys[label]])
                full_value = float(row[full_coenergy_keys[label]])
                if (abs(float(scaling["raw_sector_coenergy_j"][label]) - raw_value)
                        > IDENTITY_TOLERANCE
                        or abs(float(scaling["full_machine_coenergy_j"][label]) - full_value)
                        > IDENTITY_TOLERANCE
                        or abs(float(manifest["solve_evidence"][label]["coenergy_j"]) - raw_value)
                        > IDENTITY_TOLERANCE):
                    return False
            if (abs(float(scaling["torque_fem_sector_nm"])
                       - float(row["TorqueFEMSector [N*m]"])) > IDENTITY_TOLERANCE
                    or abs(float(scaling["torque_fem_full_machine_nm"])
                           - float(row["TorqueVirtualFEM [N*m]"])) > IDENTITY_TOLERANCE):
                return False
        return True
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def finite(row: dict[str, str], key: str) -> float:
    value = float(row[key])
    if not math.isfinite(value):
        raise ValueError(f"Non-finite {key}")
    return value


def dq_flux(phi_a: float, phi_b: float, phi_c: float) -> tuple[float, float]:
    angles = (THETA, THETA - 2 * math.pi / 3, THETA + 2 * math.pi / 3)
    values = (phi_a, phi_b, phi_c)
    phi_d = (2 / 3) * sum(value * math.cos(angle) for value, angle in zip(values, angles))
    phi_q = -(2 / 3) * sum(value * math.sin(angle) for value, angle in zip(values, angles))
    return phi_d, phi_q


def build(points_path: Path, progress_path: Path, output_path: Path) -> dict[str, object]:
    if not points_path.is_file() or sha256(points_path) != POINTS_SHA256:
        raise ValueError("Frozen qualification point hash mismatch")
    with points_path.open(newline="", encoding="ascii") as stream:
        points = list(csv.DictReader(stream))
    rows: list[dict[str, str]] = []
    if progress_path.is_file():
        with progress_path.open(newline="", encoding="ascii") as stream:
            rows = list(csv.DictReader(stream))
    expected_by_id = {point["point_id"]: point for point in points}
    expected = set(expected_by_id)
    actual = {row.get("PointID", "") for row in rows}
    complete = (
        len(points) == 10
        and len(rows) == 10
        and actual == expected
        and all(row.get("SolverStatus") == "converged" for row in rows)
    )
    errors: dict[str, list[float]] = {
        "controller_sign_identity": [],
        "stored_dq_flux_identity": [],
        "stored_phase_flux_torque_identity": [],
        "stored_abc_current_identity": [],
        "stored_coenergy_fine_identity": [],
        "stored_coenergy_coarse_identity": [],
        "stored_coenergy_fem_fine_identity": [],
        "stored_coenergy_fem_coarse_identity": [],
        "virtual_vs_phase_flux": [],
        "virtual_vs_coenergy": [],
        "phase_flux_vs_coenergy": [],
        "coenergy_step_agreement": [],
        "sector_flux_scaling_identity": [],
        "sector_coenergy_scaling_identity": [],
        "sector_torque_scaling_identity": [],
    }
    if MODE not in ("r5", "r6", "r7", "r8"):
        for name in (
            "sector_flux_scaling_identity", "sector_coenergy_scaling_identity",
            "sector_torque_scaling_identity",
        ):
            errors.pop(name)
    evidence_ok = True
    row_binding_ok = True
    if complete:
        for row in rows:
            point = expected_by_id[row["PointID"]]
            row_binding_ok = row_binding_ok and (
                row.get("PointName") == point["PointName"]
                and row.get("Region") == point["region"]
                and row.get("Purpose") == point["purpose"]
                and point.get("campaign_id") == CAMPAIGN_ID
                and all(finite(row, key) == float(point[key])
                        for key in ("Id [A]", "Iq [A]", "If [A]"))
                and row.get("Project") == PROJECT_PREFIX + point["PointName"]
                and row.get("Design") == DESIGN_NAME
                and row.get("Setup") == "Setup_Qual"
                and row.get("SourceProjectSHA256") == SOURCE_PROJECT_SHA256
                and row.get("PointsSHA256") == POINTS_SHA256
            )
            torque_virtual = finite(row, "TorqueVirtualFEM [N*m]")
            torque_controller = finite(row, "TorqueController [N*m]")
            errors["controller_sign_identity"].append(abs(torque_controller + torque_virtual))
            if MODE in ("r5", "r6", "r7", "r8"):
                errors["sector_flux_scaling_identity"].append(max(
                    abs(finite(row, full) - SECTOR_SCALE * finite(row, raw))
                    for full, raw in zip(
                        ("FluxA [Wb]", "FluxB [Wb]", "FluxC [Wb]"),
                        ("RawSectorFluxA [Wb]", "RawSectorFluxB [Wb]", "RawSectorFluxC [Wb]"),
                    )
                ))
                errors["sector_coenergy_scaling_identity"].append(max(
                    abs(finite(row, full) - SECTOR_SCALE * finite(row, raw))
                    for full, raw in zip(
                        ("CoenergyM2 [J]", "CoenergyM1 [J]", "CoenergyP1 [J]", "CoenergyP2 [J]"),
                        ("RawSectorCoenergyM2 [J]", "RawSectorCoenergyM1 [J]",
                         "RawSectorCoenergyP1 [J]", "RawSectorCoenergyP2 [J]"),
                    )
                ))
                errors["sector_torque_scaling_identity"].append(abs(
                    torque_virtual - SECTOR_SCALE * finite(row, "TorqueFEMSector [N*m]")
                ))
                row_binding_ok = row_binding_ok and finite(
                    row, "SectorToFullScale [count]"
                ) == SECTOR_SCALE

            phi_d, phi_q = dq_flux(
                finite(row, "FluxA [Wb]"), finite(row, "FluxB [Wb]"),
                finite(row, "FluxC [Wb]"),
            )
            errors["stored_dq_flux_identity"].append(max(
                abs(phi_d - finite(row, "FluxD [Wb]")),
                abs(phi_q - finite(row, "FluxQ [Wb]")),
            ))
            torque_phase = 1.5 * POLE_PAIRS * (
                phi_d * finite(row, "Iq [A]") - phi_q * finite(row, "Id [A]")
            )
            stored_phase = finite(row, "TorquePhaseFlux [N*m]")
            errors["stored_phase_flux_torque_identity"].append(abs(torque_phase - stored_phase))
            expected_abc = tuple(
                finite(row, "Id [A]") * math.cos(angle)
                - finite(row, "Iq [A]") * math.sin(angle)
                for angle in (THETA, THETA - 2 * math.pi / 3, THETA + 2 * math.pi / 3)
            )
            errors["stored_abc_current_identity"].append(max(
                abs(expected_abc[index] - finite(row, key))
                for index, key in enumerate(("Ia [A]", "Ib [A]", "Ic [A]"))
            ))

            h = math.pi / 180
            torque_fem_fine = (
                finite(row, "CoenergyP1 [J]") - finite(row, "CoenergyM1 [J]")
            ) / (2 * h)
            torque_fem_coarse = (
                finite(row, "CoenergyP2 [J]") - finite(row, "CoenergyM2 [J]")
            ) / (4 * h)
            torque_coenergy = -torque_fem_fine
            torque_coarse = -torque_fem_coarse
            errors["stored_coenergy_fine_identity"].append(
                abs(torque_coenergy - finite(row, "TorqueCoenergy [N*m]"))
            )
            errors["stored_coenergy_coarse_identity"].append(
                abs(torque_coarse - finite(row, "TorqueCoenergyCoarse [N*m]"))
            )
            errors["stored_coenergy_fem_fine_identity"].append(
                abs(torque_fem_fine - finite(row, "TorqueCoenergyFEMFine [N*m]"))
            )
            errors["stored_coenergy_fem_coarse_identity"].append(
                abs(torque_fem_coarse - finite(row, "TorqueCoenergyFEMCoarse [N*m]"))
            )
            errors["virtual_vs_phase_flux"].append(abs(torque_controller - stored_phase))
            errors["virtual_vs_coenergy"].append(abs(torque_controller - torque_coenergy))
            errors["phase_flux_vs_coenergy"].append(abs(stored_phase - torque_coenergy))
            errors["coenergy_step_agreement"].append(abs(torque_coenergy - torque_coarse))
            evidence_ok = evidence_ok and evidence_manifest_ok(row, point)

    identity_names = {
        "controller_sign_identity", "stored_dq_flux_identity",
        "stored_phase_flux_torque_identity", "stored_coenergy_fine_identity",
        "stored_coenergy_coarse_identity", "stored_abc_current_identity",
        "stored_coenergy_fem_fine_identity", "stored_coenergy_fem_coarse_identity",
        "sector_flux_scaling_identity", "sector_coenergy_scaling_identity",
        "sector_torque_scaling_identity",
    }
    checks = {}
    for name, values in errors.items():
        tolerance = IDENTITY_TOLERANCE if name in identity_names else TOLERANCE_NM
        maximum = max(values) if values else None
        checks[name] = {
            "status": "pass" if complete and maximum is not None and maximum <= tolerance else "fail",
            "maximum_abs_error": maximum,
            "tolerance": tolerance,
        }
    checks["evidence_complete"] = {"status": "pass" if complete and evidence_ok else "fail"}
    checks["row_provenance_binding"] = {"status": "pass" if complete and row_binding_ok else "fail"}
    passed = complete and all(check["status"] == "pass" for check in checks.values())
    report = {
        "overall_status": "pass" if passed else "fail",
        "completed_rows": len(rows),
        "expected_rows": 10,
        "checks": checks,
        "claims": {
            "new_task9_campaign_authorized": passed,
            "task_10_authorized": False,
            "training_on_corrected_real_fem_authorized": False,
            "note": (
                "The three-channel 1.1 N*m test is a reduced-model closure gate. "
                "Task 10 and real-data training remain blocked until a passing replacement 64-point campaign."
            ),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    root = DEFAULT_ROOT
    print(json.dumps(build(
        root / "frozen_points.csv", root / "raw" / "diagnostic_progress.csv",
        root / "requalification_report.json",
    ), indent=2))
