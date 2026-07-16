"""Offline contract tests for the Maxwell EESM adapter."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

AEDT_DIR = Path(__file__).parents[1] / "aedt"
sys.path.insert(0, str(AEDT_DIR))

from normalize_eesm_results import AdapterError, _point_id, normalize_results  # noqa: E402
from qualify_eesm_project import qualify_results  # noqa: E402


RAW_FIELDS = [
    "PointName",
    "Id [A]",
    "Iq [A]",
    "If [A]",
    "Flux_d [Wb]",
    "Flux_q [Wb]",
    "Torque [N*m]",
    "Project",
    "Design",
    "Setup",
    "RotorPosition [deg]",
    "MeshElements [count]",
    "AdaptivePasses [count]",
    "SolverStatus",
    "SolverMessage",
    "PolePairs [count]",
]


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("valid", "inconclusive"),
        ("solver_failure", "fail"),
        ("bad_units", AdapterError),
        ("duplicate_missing", AdapterError),
    ],
)
def test_adapter_contract(tmp_path: Path, variant: str, expected: object) -> None:
    points = [
        {"PointName": "zero", "region": "interior", "Id [A]": 0, "Iq [A]": 0, "If [A]": 0, "Purpose": "zero_current"},
        {"PointName": "q_sign", "region": "interior", "Id [A]": 0, "Iq [A]": 10, "If [A]": 2, "Purpose": "q_sign"},
    ]
    rows = [
        {
            "PointName": point["PointName"], "Id [A]": point["Id [A]"],
            "Iq [A]": point["Iq [A]"], "If [A]": point["If [A]"],
            "Flux_d [Wb]": 0.01, "Flux_q [Wb]": 0.02,
            "Torque [N*m]": 1.5, "Project": "motor", "Design": "EESM",
            "Setup": "Setup1", "RotorPosition [deg]": 0,
            "MeshElements [count]": 1000, "AdaptivePasses [count]": 3,
            "SolverStatus": "converged", "SolverMessage": "Normal completion",
            "PolePairs [count]": 4,
        }
        for point in points
    ]
    fields = list(RAW_FIELDS)
    if variant == "solver_failure":
        rows[1]["SolverStatus"] = "failed"
        rows[1]["SolverMessage"] = "solve failed"
        rows[1]["MeshElements [count]"] = ""
        rows[1]["AdaptivePasses [count]"] = ""
        rows[1]["Torque [N*m]"] = ""
    elif variant == "bad_units":
        fields[fields.index("Flux_d [Wb]")] = "Flux_d [mWb]"
        for row in rows:
            row["Flux_d [mWb]"] = row.pop("Flux_d [Wb]")
    elif variant == "duplicate_missing":
        rows[1] = dict(rows[0])

    points_path, raw_path = tmp_path / "points.csv", tmp_path / "raw.csv"
    canonical_path, report_path = tmp_path / "canonical.csv", tmp_path / "report.json"
    _write_csv(points_path, list(points[0]), points)
    _write_csv(raw_path, fields, rows)

    if expected is AdapterError:
        with pytest.raises(AdapterError):
            normalize_results(raw_path, points_path, canonical_path)
        return

    canonical = normalize_results(raw_path, points_path, canonical_path)
    report = qualify_results(canonical_path, report_path)
    assert len(canonical) == 2
    assert canonical[0]["role"] == "reference"
    assert canonical[0]["torque_fem_nm"] == 1.5
    assert canonical[0]["torque_controller_nm"] == -1.5
    assert json.loads(canonical[0]["raw_units"])["flux_d"] == "Wb"
    assert report["checks"]["pole_pairs"]["status"] == "pass"
    exporter = (AEDT_DIR / "export_eesm_points.py").read_text(encoding="utf-8")
    assert 'ROOT = os.path.dirname(os.path.abspath(__file__))' in exporter
    assert "No active AEDT design" in exporter
    assert "Refusing resume: progress contains failed row" in exporter
    assert 'PROJECT_NAME = "eesm_qual"' in exporter
    assert "if isinstance(value, dict):" in exporter
    assert 'POINTS = os.path.join(CAMPAIGN_ROOT, "frozen_points.csv")' in exporter
    assert 'MAX_NEW_POINTS_PER_RUN = 1' in exporter
    assert 'POINTS_SHA256 = ' in exporter
    assert '"RawABCFluxPath"' in exporter
    assert '"ConvergenceEvidencePath"' in exporter
    assert '"MeshEvidencePath"' in exporter
    assert 'project.Save()' in exporter
    assert 'ADAPTIVE_NONCONVERGENCE_MARKER = "adaptive passes did not converge"' in exporter
    assert "AEDT adaptive convergence criteria were not met" in exporter
    assert "read_prior_status" in exporter
    assert "Refusing to overwrite orphaned" in exporter
    campaign = (AEDT_DIR / "prepare_task9_campaign.py").read_text(encoding="utf-8")
    assert 'CAMPAIGN_BUDGET = 64' in campaign
    assert '"train": 40' in campaign
    assert '"selection": 12' in campaign
    assert '"reference": 8' in campaign
    assert '"scheduler_audit": 4' in campaign
    assert "refusing overwrite" in campaign.lower()
    reporter = (AEDT_DIR / "report_task9_campaign.py").read_text(encoding="utf-8")
    assert 'FEM_TO_CONTROLLER_TORQUE_SIGN = -1.0' in reporter
    assert 'TORQUE_CLOSURE_TOLERANCE_NM = 1.1' in reporter
    assert 'MESH_ELEMENT_LIMIT = 1950' in reporter
    assert '"threshold_status": "baseline_required"' in reporter
    assert "torque_sign_ok" in reporter
    assert "_torque_error_summary" in reporter
    assert '"worst_points"' in reporter
    assert "ADAPTIVE_NONCONVERGENCE_MARKER" in reporter
    assert '"promoted_surrogate": False' in reporter
    assert '"controller_ready_lut": False' in reporter
    assert '"task_10_complete": False' in reporter
    setup_remediation = (AEDT_DIR / "prepare_task9_convergence_setup.py").read_text(encoding="utf-8")
    assert 'SETUP_NAME = "Setup_Qual"' in setup_remediation
    assert "MAXIMUM_PASSES = 3" in setup_remediation
    assert '"geometry_rebuilt": False' in setup_remediation
    assert '"maxwell_solve_attempted": False' in setup_remediation
    campaign_runner = (AEDT_DIR / "run_task9_campaign.ps1").read_text(encoding="utf-8")
    assert "Wait-Process -Id $process.Id" in campaign_runner
    assert "Refusing to start while another AEDT Student process is running" in campaign_runner
    assert "Expected $nextNumber completed points after AEDT exit" in campaign_runner
    requal_preparer = (AEDT_DIR / "prepare_task9_requalification.py").read_text(encoding="utf-8")
    assert 'REQUALIFICATION_ID = "eesm_task9_torque_requal_r2_20260716"' in requal_preparer
    assert "SOURCE_PROJECT_SHA256" in requal_preparer
    assert "ANCHORS_SHA256" in requal_preparer
    assert "refusing overwrite" in requal_preparer.lower()
    requal_diagnostic = (AEDT_DIR / "diagnose_task9_torque.py").read_text(encoding="utf-8")
    assert 'TORQUE_CLOSURE_TOLERANCE_NM = 1.1' in requal_diagnostic
    assert 'TASK10_AUTHORIZED = False' in requal_diagnostic
    assert '"virtual_torque_nm"' in requal_diagnostic
    assert '"phase_flux_torque_nm"' in requal_diagnostic
    assert '"coenergy_derivative_torque_nm"' in requal_diagnostic
    assert "source_project_copy_only_no_overwrite" in requal_diagnostic
    assert "if isinstance(value, dict):" in requal_diagnostic
    requal_runner = (AEDT_DIR / "run_task9_requalification.ps1").read_text(encoding="utf-8")
    assert "Refusing to start while another AEDT Student process is running" in requal_runner
    assert "-RunScriptAndExit" in requal_runner
    corrected_builder = (AEDT_DIR / "build_corrected_eesm_r3.py").read_text(encoding="utf-8")
    assert 'PROJECT_NAME = "eesm_requal_r3"' in corrected_builder
    assert '("field_turns", rotor, ["Conductors per Pole"], 160)' in corrected_builder
    assert '("parallel_branches", stator, ["Parallel Branches"], 4)' in corrected_builder
    assert '("damper_slots", rotor, ["Damper Slots Per Pole"], 3)' in corrected_builder
    assert '("cast_rotor", rotor, ["Cast Rotor"], True)' in corrected_builder
    assert 'design.SetDesignSettings(["NAME:Design Settings Data", "ModelDepth:=", "120mm"])' in corrected_builder
    assert 'name.startswith("Bar")' in corrected_builder
    assert "editor.AssignMaterial" in corrected_builder
    assert 'contract["damper_fill_strategy"] = "separate_steel_rotor_fill"' in corrected_builder
    assert '"ParallelBranchesNum:=", 4' in corrected_builder
    assert 'DeleteBoundaries(["EndConnection1"])' in corrected_builder
    qualifier = (AEDT_DIR / "qualify_eesm_project.py").read_text(encoding="utf-8")
    assert '"q_sign_negative", "d_sign_positive"' in qualifier
    if variant == "valid":
        warning_points = [dict(point, campaign_id="task9-test", point_id=_point_id(tuple(float(point[name]) for name in ("Id [A]", "Iq [A]", "If [A]")))) for point in points]
        warning_rows = [dict(row) for row in rows]
        for point, row in zip(warning_points, warning_rows):
            row.update({
                "PointID": point["point_id"], "Role": "reference", "Region": point["region"],
                "RawABCFluxPath": str(tmp_path / "flux.csv"),
                "MeshEvidencePath": str(tmp_path / "mesh.ms"),
                "ConvergenceEvidencePath": str(tmp_path / "convergence.conv"),
                "SolverMessage": json.dumps({"errors": [], "warnings": ["Adaptive Passes did not converge based on specified criteria."]}),
            })
        warning_points_path = tmp_path / "task9_points.csv"
        warning_raw_path = tmp_path / "task9_raw.csv"
        _write_csv(warning_points_path, list(warning_points[0]), warning_points)
        _write_csv(warning_raw_path, list(warning_rows[0]), warning_rows)
        with pytest.raises(AdapterError, match="adaptive convergence criteria"):
            normalize_results(warning_raw_path, warning_points_path, tmp_path / "task9.csv")
        builder = (AEDT_DIR / "build_canonical_eesm.py").read_text(encoding="utf-8")
        assert 'DESIGN_NAME = "EESM_2D_Qual"' in builder
        assert 'SETUP_NAME = "Setup_Qual"' in builder
        assert 'OUT_JSON = os.path.join(ROOT, "eesm_model_build_status.json")' in builder
        assert '"manual", "SynM3_6p50Hz538kW.aedt"' in builder
        assert 'RMXPRT_DESIGN = "RMxprtDesign1"' in builder
        assert '"maxwell_solve_attempted": False' in builder
        assert '"MaximumPasses:=", 3' in builder
        assert "CreateMaxwell2DDesignWithAutoSetup" in builder
        direct_builder = (AEDT_DIR / "build_direct_eesm_r4.py").read_text(encoding="utf-8")
        assert 'PROJECT_NAME = "eesm_requal_direct_r4_04"' in direct_builder
        assert 'DESIGN_NAME = "EESM_2D_Direct_R4"' in direct_builder
        assert 'GEOMETRY_REVISION = "academic-direct-r4-attempt4"' in direct_builder
        assert "def create_field_sheet" in direct_builder
        assert "editor.CreateRegion" in direct_builder
        assert "GetEdgeIDsFromObject" in direct_builder
        assert '"maxwell_solve_attempted": False' in direct_builder
        assert 'project.InsertDesign("Maxwell 2D", DESIGN_NAME, "Magnetostatic", "")' in direct_builder
        assert '"Conductor number:=", turns' in direct_builder
        assert '"Task10Authorized": False' in direct_builder
        assert "AssignVectorPotential" in direct_builder
        assert "AssignTorque" in direct_builder
        assert "Analyze" not in direct_builder
        quarter_builder = (AEDT_DIR / "build_direct_eesm_r5.py").read_text(encoding="utf-8")
        assert 'PROJECT_NAME = "eesm_requal_direct_r5_01"' in quarter_builder
        assert 'DESIGN_NAME = "EESM_2D_Direct_R5_Quarter"' in quarter_builder
        assert "(22, 7.5, \"PhaseB\", -1, 4)" in quarter_builder
        assert "(3, 82.5, \"PhaseC\", -1, 5)" in quarter_builder
        assert "boundary.AssignMaster" in quarter_builder
        assert "boundary.AssignSlave" in quarter_builder
        assert '"Master:=", "Quarter_Independent"' in quarter_builder
        assert '"SameAsMaster:=", False' in quarter_builder
        assert '"Torque_FEM", "4*TorqueRotor.Torque"' in quarter_builder
        assert '"rotate_without_reclip"' in quarter_builder
        assert '"keep_fixed_axisymmetric": ["RotorYoke", "Shaft"]' in quarter_builder
        assert '"aedt_magnetostatic_symmetry_multiplier_used": False' in quarter_builder
        assert "Analyze" not in quarter_builder
        r6_builder = (AEDT_DIR / "build_direct_eesm_r6.py").read_text(encoding="utf-8")
        assert 'base.PROJECT_NAME = "eesm_requal_direct_r6_01"' in r6_builder
        assert 'base.DESIGN_NAME = "EESM_2D_Direct_R6_Quarter"' in r6_builder
        assert '"ReverseV:=", False' in r6_builder
        assert '"ReverseU:=", False' in r6_builder
        assert '"SameAsMaster:=", False' in r6_builder
        assert 'base.configure_boundaries = configure_boundaries' in r6_builder
        assert "Analyze" not in r6_builder
        r6_verifier = (AEDT_DIR / "verify_direct_eesm_r6.py").read_text(encoding="utf-8")
        assert 'saved_boundary_flag(project_text, "Quarter_Dependent", "ReverseU", "false")' in r6_verifier
        assert 'require(observed_map == expected_map, "Exact terminal map drifted")' in r6_verifier
        assert '"Expected exactly 19 sheets"' in r6_verifier
        r7_builder = (AEDT_DIR / "build_direct_eesm_r7.py").read_text(encoding="utf-8")
        assert 'base.PROJECT_NAME = "eesm_requal_direct_r7_01"' in r7_builder
        assert 'base.DESIGN_NAME = "EESM_2D_Direct_R7_Quarter"' in r7_builder
        assert 'OUTER_RADIUS_MM = 90.0' in r7_builder
        assert '"DllName:=", "RMxprt/Band"' in r7_builder
        assert '"InfoCore", "1"' in r7_builder
        assert '"Tool Parts:=", SHARED_TOOL_NAME' in r7_builder
        assert 'base.clip_to_quadrant = _defer_clip' in r7_builder
        assert 'base.build_region = build_region_and_shared_clip' in r7_builder
        assert '"ReverseU:=", False' in r7_builder
        assert '"isolated_change_from_r6"' in r7_builder
        assert "editor.CreateRegion" not in r7_builder
        assert "Analyze" not in r7_builder
        r7_verifier = (AEDT_DIR / "verify_direct_eesm_r7.py").read_text(encoding="utf-8")
        assert '"RMxprt OuterRegion did not replace generic Region"' in r7_verifier
        assert '"Shared clipping Tool was not consumed"' in r7_verifier
        assert '"Generic CreateRegion history is prohibited in r7"' in r7_verifier
        assert '"Per-object quadrant clip history is prohibited in r7"' in r7_verifier
        assert '"Independent edge is not exactly the 0..90 mm x radial edge"' in r7_verifier
        assert '"Dependent edge is not exactly the 0..90 mm y radial edge"' in r7_verifier
        assert '"maxwell_solve_attempted": False' in r7_verifier
        r7_freezer = (AEDT_DIR / "prepare_task9_requalification_r3.py").read_text(encoding="utf-8")
        assert 'CAMPAIGN_ID = "eesm_task9_torque_requal_r7_20260716"' in r7_freezer
        assert 'REVISION_ID = "eesm_requal_direct_r7_01"' in r7_freezer
        assert '"model_build_status_attempt1.json"' in r7_freezer
        assert '"model_verification_attempt1.json"' in r7_freezer
        r7_session = (AEDT_DIR / "prepare_task9_r3_anchor_session.py").read_text(encoding="utf-8")
        assert '"task9_r7_sessions"' in r7_session
        assert 'PROJECT_PREFIX = "eesm_requal_r7_anchor_"' in r7_session
        assert 'DESIGN_NAME = "EESM_2D_Direct_R7_Quarter"' in r7_session
        assert 'POINTS_SHA256 = "43b87920ab04d8f9aa371a739a2d0dc4c3464789a4d702442df60d6a1488e7b1"' in r7_session
        r5_runner = (AEDT_DIR / "run_task9_requalification_r3_anchor.py").read_text(encoding="utf-8")
        assert 'SOURCE_PROJECT_SHA256 = "4fccd71493d0864db866ff0c55d01fe0e3fb304da76f5feb55ef3fe2ffabe830"' in r5_runner
        assert 'DESIGN_NAME = "EESM_2D_Direct_R5_Quarter"' in r5_runner
        assert '"PoleAssembly_01", "Field_P01_NegT", "Field_P01_PosT"' in r5_runner
        assert 'SECTOR_SCALE = 4.0' in r5_runner
        assert '"Torque_FEM_Sector"' in r5_runner
        assert '"RawSectorFluxA [Wb]"' in r5_runner
        assert '"RawSectorCoenergyM2 [J]"' in r5_runner
        assert "Torque_FEM != 4*Torque_FEM_Sector" in r5_runner
        r5_reporter = (AEDT_DIR / "report_task9_requalification_r3.py").read_text(encoding="utf-8")
        assert '"sector_flux_scaling_identity"' in r5_reporter
        assert '"sector_coenergy_scaling_identity"' in r5_reporter
        assert '"sector_torque_scaling_identity"' in r5_reporter
        r6_freezer = (AEDT_DIR / "prepare_task9_requalification_r3.py").read_text(encoding="utf-8")
        assert 'CAMPAIGN_ID = "eesm_task9_torque_requal_r6_20260716"' in r6_freezer
        assert 'REVISION_ID = "eesm_requal_direct_r6_01"' in r6_freezer
        assert '"model_build_status_attempt2.json"' in r6_freezer
        assert '"model_verification_attempt2.json"' in r6_freezer
        r6_session = (AEDT_DIR / "prepare_task9_r3_anchor_session.py").read_text(encoding="utf-8")
        assert '"task9_r6_sessions"' in r6_session
        assert 'PROJECT_PREFIX = "eesm_requal_r6_anchor_"' in r6_session
        assert 'DESIGN_NAME = "EESM_2D_Direct_R6_Quarter"' in r6_session
        assert 'POINTS_SHA256 = "de5374112705f8274ab3fbf276fc692efe404928333c1bac0b9883db1db16ad2"' in r6_session
        assert 'elif MODE == "r6":' in r5_runner
        assert '"EESM_R6_CAMPAIGN_ROOT"' in r5_runner
        assert 'SOURCE_PROJECT_SHA256 = "404a4b6f5a7e91f9c3bd69087c5a50e43ac51b22b899cbbb168e5e55feffbbcd"' in r5_runner
        assert 'elif MODE == "r6":' in r5_reporter
        assert 'PROJECT_PREFIX = "eesm_requal_r6_anchor_"' in r5_reporter
        assert 'elif MODE == "r7":' in r5_runner
        assert '"EESM_R7_CAMPAIGN_ROOT"' in r5_runner
        assert 'SOURCE_PROJECT_SHA256 = "527d2430823b981f6eff753d8044abc061029d12446c9b17196d16c3acd53bf1"' in r5_runner
        assert 'raw_sector_evidence_preserved": MODE in ("r5", "r6", "r7", "r8")' in r5_runner
        assert 'elif MODE == "r7":' in r5_reporter
        assert 'PROJECT_PREFIX = "eesm_requal_r7_anchor_"' in r5_reporter
        r8_builder = (AEDT_DIR / "build_direct_eesm_r8.py").read_text(encoding="utf-8")
        assert 'base.PROJECT_NAME = "eesm_requal_direct_r8_01"' in r8_builder
        assert 'base.DESIGN_NAME = "EESM_2D_Direct_R8_Quarter"' in r8_builder
        assert 'import build_direct_eesm_r7 as r7' in r8_builder
        assert 'builtins.oDesktop = oDesktop' in r8_builder
        assert '_r7_build = r7.build' in r8_builder
        assert '"ReverseV:=", False' in r8_builder
        assert '"ReverseU:=", True' in r8_builder
        assert '"SameAsMaster:=", False' in r8_builder
        assert '"isolated_change_from_r7"' in r8_builder
        assert '"dependent_boundary_direction_only"' in r8_builder
        assert '"a07337b394a9bba6d78453f2478f0dba828829f19778bee65248129ded25719b"' in r8_builder
        assert "Analyze" not in r8_builder
        r8_verifier = (AEDT_DIR / "verify_direct_eesm_r8.py").read_text(encoding="utf-8")
        assert '"r8 drifted from r7 outside boundary direction: "' in r8_verifier
        assert '"Independent edge is not exactly the 0..90 mm x radial edge"' in r8_verifier
        assert '"Dependent edge is not exactly the 0..90 mm y radial edge"' in r8_verifier
        assert '"ReverseU=true" in dependent' in r8_verifier
        assert '"ReverseV=false" in independent' in r8_verifier
        assert '"SameAsMaster=false" in dependent' in r8_verifier
        assert '"maxwell_solve_attempted": False' in r8_verifier
        assert "Analyze" not in r8_verifier
        correction_path = (
            AEDT_DIR / "solver_evidence" /
            "post_r7_boundary_direction_research_correction.json"
        )
        correction = json.loads(correction_path.read_text(encoding="utf-8"))
        assert correction["preserves_r7_failure_evidence"] is True
        assert correction["qualification_authorized"] is False
        assert correction["new_task9_campaign_authorized"] is False
        assert correction["task_10_authorized"] is False
        assert correction["training_on_corrected_real_fem_authorized"] is False
        matrix = correction["interaction_matrix"]
        assert [(row["revision"], row["dependent_reverse_u"])
                for row in matrix] == [
            ("r5", True), ("r6", False), ("r7", False),
            ("r8_proposed_no_solve_source", True),
        ]
        assert matrix[-1]["campaign_authorized"] is False
        assert correction["sources"]["local_generated_maxwell_2d_motor_script"]["sha256"] == (
            "a07337b394a9bba6d78453f2478f0dba828829f19778bee65248129ded25719b"
        )
        r8_freezer = (AEDT_DIR / "prepare_task9_requalification_r3.py").read_text(encoding="utf-8")
        assert 'CAMPAIGN_ID = "eesm_task9_torque_requal_r8_20260716"' in r8_freezer
        assert 'PROJECT_SHA256 = "28defa3863eb863de5b0a0deed826fc4a686116acd2c9d84804d93ef72cb0d98"' in r8_freezer
        assert 'EXPECTED_MODEL_BUILD_STATUS_SHA256 = "74ac19578532ddc883f1d46ab4c2acc0ca5cbee346f1e65d6078557b5d03cd64"' in r8_freezer
        assert 'EXPECTED_MODEL_STATUS_SHA256 = "7b471ea41b17bd8c93f747c17dd55b5123c0618bbe6fd600dc00d736dbbf1c44"' in r8_freezer
        assert 'EXPECTED_CRASH_DUMP_SHA256 = "9eb5b2afbbe90d44459305d3d00455a7bc1512d71aff1726f387fa1d81d2e062"' in r8_freezer
        r8_session = (AEDT_DIR / "prepare_task9_r3_anchor_session.py").read_text(encoding="utf-8")
        assert 'elif MODE == "r8":' in r8_session
        assert '"task9_r8_sessions"' in r8_session
        assert 'PROJECT_PREFIX = "eesm_requal_r8_anchor_"' in r8_session
        assert 'POINTS_SHA256 = "b7f8a469ab3fc7472fea3ef2eac7fdf9140f9488c884aa978d8e7409efbca77b"' in r8_session
        assert 'DESIGN_NAME = "EESM_2D_Direct_R8_Quarter"' in r8_session
        assert 'elif MODE == "r8":' in r5_runner
        assert '"EESM_R8_CAMPAIGN_ROOT"' in r5_runner
        assert 'SOURCE_PROJECT_SHA256 = "28defa3863eb863de5b0a0deed826fc4a686116acd2c9d84804d93ef72cb0d98"' in r5_runner
        assert 'raw_sector_evidence_preserved": MODE in ("r5", "r6", "r7", "r8")' in r5_runner
        assert 'elif MODE == "r8":' in r5_reporter
        assert 'PROJECT_PREFIX = "eesm_requal_r8_anchor_"' in r5_reporter
        assert (AEDT_DIR / "prepare_task9_requalification_r8.py").is_file()
        assert (AEDT_DIR / "prepare_task9_r8_anchor_session.py").is_file()
        assert (AEDT_DIR / "run_task9_requalification_r8_anchor.py").is_file()
        assert (AEDT_DIR / "report_task9_requalification_r8.py").is_file()
        r9_builder = (AEDT_DIR / "build_direct_eesm_r9.py").read_text(encoding="utf-8")
        assert 'base.PROJECT_NAME = "eesm_requal_direct_r9_01"' in r9_builder
        assert 'base.DESIGN_NAME = "EESM_2D_Direct_R9_Quarter"' in r9_builder
        assert 'import build_direct_eesm_r8 as r8' in r9_builder
        assert '_r8_build = r8.build' in r9_builder
        assert '_r8_validate_inventory = base.validate_inventory' in r9_builder
        assert '"NAME:SurfApprox_Main"' in r9_builder
        assert '"Objects:=", list(SURFACE_APPROX_OBJECTS)' in r9_builder
        assert '"SurfDevChoice:=", 2' in r9_builder
        assert '"SurfDev:=", "0.09mm"' in r9_builder
        assert '"NormalDevChoice:=", 2' in r9_builder
        assert '"NormalDev:=", "15deg"' in r9_builder
        assert '"AspectRatioChoice:=", 1' in r9_builder
        assert '"Stator", "RotorYoke", "PoleAssembly_01", "OuterRegion", "Shaft"' in r9_builder
        assert '"generated_surface_approximation_only"' in r9_builder
        assert 'payload["campaign_binding_authorized"] = False' in r9_builder
        assert "Analyze" not in r9_builder
        r9_verifier = (AEDT_DIR / "verify_direct_eesm_r9.py").read_text(encoding="utf-8")
        assert 'R8_STATUS_SHA256 = "74ac19578532ddc883f1d46ab4c2acc0ca5cbee346f1e65d6078557b5d03cd64"' in r9_verifier
        assert 'R8_VERIFICATION_SHA256 = "7b471ea41b17bd8c93f747c17dd55b5123c0618bbe6fd600dc00d736dbbf1c44"' in r9_verifier
        assert '"r9 drifted from r8 outside surface approximation: "' in r9_verifier
        assert 'set(build_status) == expected_keys' in r9_verifier
        assert 'mesh.GetOperationNames("All")' in r9_verifier
        assert 'editor.GetObjectIDByName(name)' in r9_verifier
        assert '"CurvedSurfaceApproxChoice=\'ManualSettings\'"' in r9_verifier
        assert '"SurfDev=\'0.09mm\'"' in r9_verifier
        assert '"NormalDev=\'15deg\'"' in r9_verifier
        assert '"maxwell_solve_attempted": False' in r9_verifier
        assert "Analyze" not in r9_verifier
        r9_research_path = (
            AEDT_DIR / "solver_evidence" /
            "post_r8_surface_approximation_research.json"
        )
        r9_research = json.loads(r9_research_path.read_text(encoding="utf-8"))
        assert r9_research["preserves_r8_failure_evidence"] is True
        assert r9_research["qualification_authorized"] is False
        assert r9_research["new_task9_campaign_authorized"] is False
        assert r9_research["task_10_authorized"] is False
        assert r9_research["training_on_corrected_real_fem_authorized"] is False
        assert r9_research["r8_failure_evidence"]["sha256"] == (
            "b10b91d879b09e89e565741a7ffd699e2d48eb0ffd3f24d9c81c78e02207aba6"
        )
        assert r9_research["r9_surface_approximation_objects"] == [
            "Stator", "RotorYoke", "PoleAssembly_01", "OuterRegion", "Shaft",
        ]
        assert r9_research["source"]["generated_operation"] == {
            "name": "SurfApprox_Main",
            "objects": ["Stator", "Rotor", "Band", "OuterRegion", "InnerRegion", "Shaft"],
            "surf_dev_choice": 2,
            "surf_dev": "0.09mm",
            "normal_dev_choice": 2,
            "normal_dev": "15deg",
            "aspect_ratio_choice": 1,
        }
        assert not (AEDT_DIR / "prepare_task9_requalification_r9.py").exists()
        assert not (AEDT_DIR / "prepare_task9_r9_anchor_session.py").exists()
        assert not (AEDT_DIR / "run_task9_requalification_r9_anchor.py").exists()
        assert not (AEDT_DIR / "report_task9_requalification_r9.py").exists()
        r9_audit = (AEDT_DIR / "audit_active_r9_mesh_operation_type.py").read_text(
            encoding="utf-8"
        )
        assert '"Surface Approximation Based"' in r9_audit
        assert 'mesh.GetOperationNames(operation_type)' in r9_audit
        assert '"design_mutation_attempted": False' in r9_audit
        assert "Analyze" not in r9_audit
        r9_attempt2 = (AEDT_DIR / "build_direct_eesm_r9_02.py").read_text(
            encoding="utf-8"
        )
        assert 'base.PROJECT_NAME = "eesm_requal_direct_r9_02"' in r9_attempt2
        assert 'import build_direct_eesm_r9 as r9' in r9_attempt2
        assert 'CONFIRMED_OPERATION_TYPE = "Surface Approximation Based"' in r9_attempt2
        assert 'GetOperationNames(' in r9_attempt2
        assert 'CONFIRMED_OPERATION_TYPE' in r9_attempt2
        assert 'r9.configure_surface_approximation(design)' in r9_attempt2
        assert '"mesh_assignment_changed": False' in r9_attempt2
        assert '"physics_changed": False' in r9_attempt2
        assert '"b85683096f880155870bc395f98d6092e04e70dd95575520d155e20fbb9b88f3"' in r9_attempt2
        assert "Analyze" not in r9_attempt2
        r9_attempt2_verifier = (
            AEDT_DIR / "verify_direct_eesm_r9_02.py"
        ).read_text(encoding="utf-8")
        assert 'AUDIT_SHA256 = "b85683096f880155870bc395f98d6092e04e70dd95575520d155e20fbb9b88f3"' in r9_attempt2_verifier
        assert 'mesh.GetOperationNames(' in r9_attempt2_verifier
        assert 'CONFIRMED_OPERATION_TYPE' in r9_attempt2_verifier
        assert 'normalize(mesh.GetOperationNames("All")) == []' in r9_attempt2_verifier
        assert '"Attempt2 introspection-only correction contract drifted"' in r9_attempt2_verifier
        assert '"maxwell_solve_attempted": False' in r9_attempt2_verifier
        assert "Analyze" not in r9_attempt2_verifier
        r9_mesh_diagnostic = (
            AEDT_DIR / "generate_mesh_direct_eesm_r9_02.py"
        ).read_text(encoding="utf-8")
        assert 'SOURCE_PROJECT_SHA256 = "7b7fbd31320afc64c4f031fb8480ebca89071b9b43e2945f47e8a6243cf60cb3"' in r9_mesh_diagnostic
        assert 'design.GenerateMesh(["Setup_Qual"])' in r9_mesh_diagnostic
        assert '"field_solve_attempted": False' in r9_mesh_diagnostic
        assert '"training_authorized": False' in r9_mesh_diagnostic
        assert "Analyze" not in r9_mesh_diagnostic
        r9_mesh_runner = (
            AEDT_DIR / "run_r9_mesh_diagnostic.ps1"
        ).read_text(encoding="utf-8")
        assert "eesm_requal_direct_r9_02_meshdiag_02" in r9_mesh_runner
        assert "Copy-Item -LiteralPath $source -Destination $target" in r9_mesh_runner
        assert "-RunScriptAndExit" in r9_mesh_runner
        assert "-ng" in r9_mesh_runner
        assert "Analyze" not in r9_mesh_runner
        r9_solve_diagnostic = (
            AEDT_DIR / "solve_direct_eesm_r9_02.py"
        ).read_text(encoding="utf-8")
        assert 'design.Analyze("Setup_Qual")' in r9_solve_diagnostic
        assert '"campaign_binding_authorized": False' in r9_solve_diagnostic
        assert '"training_authorized": False' in r9_solve_diagnostic
        assert "GetMessages" not in r9_solve_diagnostic
        assert "design.Solve" not in r9_solve_diagnostic
        r9_solve_runner = (
            AEDT_DIR / "run_r9_solve_diagnostic.ps1"
        ).read_text(encoding="utf-8")
        assert "eesm_requal_direct_r9_02_solvediag_02" in r9_solve_runner
        assert "Copy-Item -LiteralPath $source -Destination $target" in r9_solve_runner
        assert "-RunScriptAndExit" in r9_solve_runner
        assert "-ng" in r9_solve_runner
        r9_generated_recovery = (
            AEDT_DIR / "solve_generated_geometry_r9_03.py"
        ).read_text(encoding="utf-8")
        assert 'SOURCE_PROJECT_SHA256 = "e99d4aba12ac4dc139e8797482bb54c2240a1134d277ef74ee7fcb4f19aa57a9"' in r9_generated_recovery
        assert '["NAME:If", "Value:=", "2A"]' in r9_generated_recovery
        assert 'design.Analyze("Setup_Qual")' in r9_generated_recovery
        assert "Rotate" not in r9_generated_recovery
        assert "GetMessages" not in r9_generated_recovery
        assert '"training_authorized": False' in r9_generated_recovery
        r9_generated_runner = (
            AEDT_DIR / "run_r9_generated_geometry_diagnostic.ps1"
        ).read_text(encoding="utf-8")
        assert "eesm_requal_generated_r9_03_nominal_01" in r9_generated_runner
        assert "Copy-Item -LiteralPath $source -Destination $target" in r9_generated_runner
        assert "-RunScriptAndExit" in r9_generated_runner
        assert "-ng" in r9_generated_runner
    if variant == "solver_failure":
        assert canonical[1]["mesh_elements"] is None
        assert canonical[1]["adaptive_passes"] is None
    assert report["overall_status"] == expected
    assert report["checks"]["torque_closure"]["status"] == "inconclusive"
    assert "Task 8" in report["checks"]["torque_closure"]["reason"]
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
