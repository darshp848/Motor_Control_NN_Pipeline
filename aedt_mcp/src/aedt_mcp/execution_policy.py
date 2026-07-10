"""Sandbox-aware execution policy for AEDT MCP tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAPABILITIES_PATH = Path(__file__).resolve().parent / "state" / "capabilities.json"


class Tier(IntEnum):
    SAFE_AUTOMATIC = 0
    CAUTIOUS_WORKSPACE_ONLY = 1
    USER_RUN_NATIVE_POWERSHELL = 2
    MANUAL_AEDT_GUI = 3


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    tier: Tier
    reason: str
    risk_level: str = "low"


TIER_DESCRIPTIONS = {
    Tier.SAFE_AUTOMATIC: "Read workspace files, parse logs, inspect copied config, generate scripts/docs, and run non-AEDT tests.",
    Tier.CAUTIOUS_WORKSPACE_ONLY: "Create project-local folders and write generated procedures under docs/procedures or scripts/generated.",
    Tier.USER_RUN_NATIVE_POWERSHELL: "Requires native user-run PowerShell because Codex cannot reliably perform the action.",
    Tier.MANUAL_AEDT_GUI: "Requires manual AEDT GUI interaction.",
}

FAILURE_CATEGORIES = [
    "filesystem_permission",
    "aedt_config",
    "codex_sandbox",
    "pyaedt_attach",
    "pyaedt_student_attach_detection_failure",
    "pyaedt_launch_failed",
    "pyaedt_license_error",
    "pyaedt_grpc_security_mode_error",
    "pyaedt_project_open_failed",
    "pyaedt_design_missing",
    "pyaedt_setup_missing",
    "pyaedt_solve_failed",
    "pyaedt_report_export_failed",
    "pyaedt_nonfinite_flux_data",
    "grpc_transport",
    "license",
    "process_hang",
    "duplicate_session",
    "aedt_duplicate_processes",
    "aedt_port_conflict",
    "port_conflict",
    "unknown",
]

PYAEDT_TOOL_NAMES = {
    "open_design",
    "save_project",
    "close_project",
    "create_box",
    "create_cylinder",
    "create_circle",
    "create_rectangle",
    "create_polyline",
    "boolean_op",
    "duplicate_around_axis",
    "duplicate_along_line",
    "move_translate",
    "rotate",
    "import_geometry",
    "add_material",
    "assign_material",
    "list_materials",
    "set_variable",
    "list_variables",
    "create_coil",
    "create_winding",
    "assign_current",
    "assign_voltage",
    "assign_magnetization",
    "assign_rotate_motion",
    "create_boundary_dependent",
    "assign_length_mesh",
    "assign_skin_depth_mesh",
    "surface_mesh",
    "create_setup",
    "edit_setup",
    "delete_setup",
    "analyze_setup",
    "get_solve_status",
    "get_solution_data",
    "get_torque",
    "get_flux_linkage",
    "get_winding_inductance",
    "create_parametric_setup",
    "add_variation",
    "analyze_parametric",
    "get_variation_table",
    "get_field_points_on_contour",
    "export_field_on_volume",
    "field_calculator_eval",
    "run_design_vector",
}

SAFE_TOOL_NAMES = {
    "list_designs",
    "aedt.safe_status",
    "aedt.diagnose_environment",
    "aedt.parse_logs",
    "aedt.classify_failure",
    "aedt.generate_launch_procedure",
    "aedt.generate_attach_test",
    "aedt.write_procedure",
    "aedt.resume_from_user_output",
    "aedt.generate_scriptenv_probe",
    "aedt.resume_scriptenv_probe",
    "aedt.generate_project_probe_procedure",
    "aedt.resume_project_probe",
    "aedt.generate_fem_export_plan",
    "aedt.generate_fem_export_procedure",
    "aedt.resume_fem_export",
    "aedt.fem_export_status",
    "aedt.generate_pyaedt_launch_owned_probe",
    "aedt.resume_pyaedt_launch_owned_probe",
    "aedt.generate_pyaedt_project_probe_procedure",
    "aedt.resume_pyaedt_project_probe",
    "aedt.generate_pyaedt_fem_export_procedure",
    "aedt.resume_pyaedt_fem_export",
    "aedt.pyaedt_export_status",
    "aedt.generate_aedt_process_inventory",
    "aedt.generate_stop_duplicate_aedt_procedure",
    "aedt.resume_process_cleanup",
}

LOG_PATTERNS = [
    "temp",
    "C:/temp",
    "C:\\temp",
    "read only",
    "readonly",
    "denied",
    "OneDrive",
    "ProjectDirectory",
    "grpc",
    "GRPC server running",
    "port",
    "insecure",
    "secure",
    "license",
    "student",
    "timeout",
    "exception",
    "ansysedtsv",
    "ansysedt",
    "no active session",
    "new_desktop",
    "50051",
    "50052",
    "attempted to launch",
    "Opening a new AEDT session",
    "pyaedt_launch_owned",
    "pyaedt",
    "blocked by generated script",
    "ScriptEnv",
    "non-finite",
    "missing design",
    "missing setup",
]


def load_capabilities() -> dict[str, Any]:
    return json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))


def decide_tool(name: str) -> PolicyDecision:
    if name in SAFE_TOOL_NAMES:
        return PolicyDecision(True, Tier.SAFE_AUTOMATIC, "Safe operator-guided tool.")
    if name in PYAEDT_TOOL_NAMES:
        return PolicyDecision(
            False,
            Tier.USER_RUN_NATIVE_POWERSHELL,
            f"Tool '{name}' requires a live AEDT/PyAEDT session. Codex must generate a user-run procedure instead.",
            "medium",
        )
    return PolicyDecision(False, Tier.USER_RUN_NATIVE_POWERSHELL, f"Tool '{name}' has no safe execution policy.", "medium")


def classify_path(path: str | Path) -> PolicyDecision:
    raw = str(path)
    lowered = raw.lower().replace("/", "\\")
    if lowered.startswith("c:\\temp"):
        return PolicyDecision(False, Tier.USER_RUN_NATIVE_POWERSHELL, "C:\\temp is known unavailable from Codex.", "medium")
    if "onedrive\\documents\\ansoft" in lowered:
        return PolicyDecision(False, Tier.USER_RUN_NATIVE_POWERSHELL, "OneDrive Documents Ansoft config paths are user-run only.", "medium")
    if "program files" in lowered:
        return PolicyDecision(False, Tier.USER_RUN_NATIVE_POWERSHELL, "Program Files is outside the workspace boundary.", "high")
    try:
        Path(path).resolve().relative_to(PROJECT_ROOT.resolve())
    except (OSError, ValueError):
        return PolicyDecision(False, Tier.USER_RUN_NATIVE_POWERSHELL, "Path is outside the workspace.", "medium")
    return PolicyDecision(True, Tier.CAUTIOUS_WORKSPACE_ONLY, "Path is workspace-local.")


def user_action_required(
    *,
    reason: str,
    procedure_id: str,
    commands: list[str],
    expected_output: list[str],
    paste_back: list[str],
    log_paths: list[str] | None = None,
    cleanup: list[str] | None = None,
    risk_level: str = "medium",
) -> dict[str, Any]:
    return {
        "status": "user_action_required",
        "reason": reason,
        "risk_level": risk_level,
        "procedure_id": procedure_id,
        "commands": commands,
        "expected_output": expected_output,
        "paste_back": paste_back,
        "log_paths": log_paths or [],
        "cleanup": cleanup or [],
    }


def blocked_tool_response(name: str) -> dict[str, Any]:
    decision = decide_tool(name)
    if name == "analyze_setup":
        procedure_id = "solve_user_run"
    elif name == "open_design":
        procedure_id = "open_design_user_run"
    else:
        procedure_id = f"{name}_user_run"
    return user_action_required(
        reason=decision.reason,
        risk_level=decision.risk_level,
        procedure_id=procedure_id,
        commands=[
            "$ErrorActionPreference = 'Stop'",
            f"$projectRoot = '{PROJECT_ROOT}'",
            "Set-Location -LiteralPath $projectRoot",
            "Run `aedt.generate_launch_procedure`, then `aedt.generate_attach_test`, and paste the output back.",
        ],
        expected_output=["A running AEDT gRPC server and a successful attach test."],
        paste_back=["The launch log tail.", "The attach test log contents."],
        log_paths=["tmp/aedt_jobs"],
        cleanup=["Do not use new_desktop=True during attach tests.", "Do not launch graphical AEDT from Codex."],
    )


def classify_failure_text(text: str) -> str:
    lowered = text.lower()
    if "c:/temp" in lowered or "c:\\temp" in lowered or "read only" in lowered or "readonly" in lowered or "denied" in lowered:
        return "filesystem_permission"
    if "projectdirectory" in lowered or "tempdirectory" in lowered or "onedrive" in lowered:
        return "aedt_config"
    if "codex" in lowered or "sandbox" in lowered:
        return "codex_sandbox"
    if (
        "opening a new aedt session" in lowered
        or "no active aedt grpc session found" in lowered
    ):
        return "pyaedt_student_attach_detection_failure"
    if (
        "no active session" in lowered
        or "new_desktop" in lowered
        or "failed to start new aedt grpc session" in lowered
        or "attempted to launch aedt" in lowered
        or "blocked by generated script" in lowered
    ):
        return "pyaedt_attach"
    if "pyaedt" in lowered and "license" in lowered:
        return "pyaedt_license_error"
    if "pyaedt" in lowered and ("secure" in lowered or "insecure" in lowered or "mtls" in lowered or "wnua" in lowered):
        return "pyaedt_grpc_security_mode_error"
    if "pyaedt" in lowered and ("project_open_failed" in lowered or "open project" in lowered):
        return "pyaedt_project_open_failed"
    if "missing design" in lowered:
        return "pyaedt_design_missing"
    if "missing setup" in lowered:
        return "pyaedt_setup_missing"
    if "pyaedt" in lowered and ("analyze" in lowered or "solve" in lowered):
        return "pyaedt_solve_failed"
    if "pyaedt" in lowered and ("report" in lowered or "fluxlinkage" in lowered or "solution data" in lowered):
        return "pyaedt_report_export_failed"
    if "non-finite" in lowered or "nonfinite" in lowered:
        return "pyaedt_nonfinite_flux_data"
    if "pyaedt_launch_failed" in lowered or ("pyaedt" in lowered and "failed to start" in lowered):
        return "pyaedt_launch_failed"
    if "grpc" in lowered or "insecure" in lowered or "secure" in lowered:
        return "grpc_transport"
    if "license" in lowered or "student" in lowered:
        return "license"
    if "timeout" in lowered or "hang" in lowered:
        return "process_hang"
    if "duplicate" in lowered or "second aedt" in lowered:
        return "aedt_duplicate_processes"
    if "port" in lowered and ("in use" in lowered or "conflict" in lowered or "already" in lowered):
        return "aedt_port_conflict"
    return "unknown"
