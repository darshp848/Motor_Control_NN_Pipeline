"""Safe operator-guided tools that do not launch AEDT."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import execution_policy as policy
from . import procedures, pyaedt_workflow, scriptenv_workflow


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(policy.PROJECT_ROOT))
    except ValueError:
        return str(path)


def safe_status() -> dict[str, Any]:
    caps = policy.load_capabilities()
    return {
        "status": "ok",
        "project_root": str(policy.PROJECT_ROOT),
        "capabilities": caps,
        "execution_tiers": {str(int(tier)): text for tier, text in policy.TIER_DESCRIPTIONS.items()},
        "preferred_paths": {
            key: {
                "path": value,
                "exists": (policy.PROJECT_ROOT / value).exists(),
                "policy": policy.classify_path(policy.PROJECT_ROOT / value).__dict__,
            }
            for key, value in caps["preferred_paths"].items()
        },
        "blocked_tool_count": len(policy.PYAEDT_TOOL_NAMES),
    }


def classify_failure(text: str) -> dict[str, Any]:
    return {
        "category": policy.classify_failure_text(text),
        "known_categories": policy.FAILURE_CATEGORIES,
    }


def parse_logs(log_dir: str = "tmp/aedt_jobs", max_matches: int = 200) -> dict[str, Any]:
    base = policy.PROJECT_ROOT / log_dir
    matches = []
    files = []
    if base.exists():
        for path in sorted(base.rglob("*")):
            if not path.is_file() or not (path.name.endswith(".log") or path.name.endswith(".err.log")):
                continue
            files.append(_relative(path))
            for line_no, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
                if any(pattern.lower() in line.lower() for pattern in policy.LOG_PATTERNS):
                    matches.append(
                        {
                            "file": _relative(path),
                            "line": line_no,
                            "text": line[:500],
                            "category": policy.classify_failure_text(line),
                        }
                    )
                    if len(matches) >= max_matches:
                        break
            if len(matches) >= max_matches:
                break
    return {
        "status": "ok",
        "log_dir": log_dir,
        "files_scanned": files,
        "matches": matches,
        "categories": sorted({row["category"] for row in matches}),
        "patterns": policy.LOG_PATTERNS,
    }


def diagnose_environment() -> dict[str, Any]:
    caps = policy.load_capabilities()
    hardcoded_hits = []
    for root in [policy.PROJECT_ROOT / "src", policy.PROJECT_ROOT / "scripts", policy.PROJECT_ROOT / "docs"]:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py", ".ps1", ".md", ".json"}:
                text = path.read_text(errors="replace")
                if "C:\\temp" in text or "C:/temp" in text or "OneDrive" in text:
                    hardcoded_hits.append(_relative(path))
    return {
        "status": "ok",
        "capabilities_loaded": True,
        "known_limits": caps["limits"],
        "preferred_paths": safe_status()["preferred_paths"],
        "hardcoded_path_hits": hardcoded_hits,
        "log_summary": parse_logs(),
    }


def generate_launch_procedure(port: int = 50052) -> dict[str, Any]:
    return procedures.launch_procedure(port)


def generate_attach_test(port: int = 50052, include_scriptenv: bool = True) -> dict[str, Any]:
    return procedures.attach_test_procedure(port, include_scriptenv)


def generate_scriptenv_probe(port: int = 50052, timeout_seconds: int = 45) -> dict[str, Any]:
    return scriptenv_workflow.scriptenv_probe_procedure(port=port, timeout_seconds=timeout_seconds)


def resume_scriptenv_probe(output: str) -> dict[str, Any]:
    return scriptenv_workflow.parse_prefixed_json(output)


def generate_project_probe_procedure(
    project: str,
    port: int = 50052,
    job_id: str = "project_probe",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    return scriptenv_workflow.project_probe_procedure(
        project=project,
        port=port,
        job_id=job_id,
        timeout_seconds=timeout_seconds,
    )


def resume_project_probe(output: str) -> dict[str, Any]:
    return scriptenv_workflow.parse_prefixed_json(output)


def generate_fem_export_plan(stage: str = "smoke", i_rated: float = 150.0, theta_re: float = 0.0) -> dict[str, Any]:
    return scriptenv_workflow.fem_export_plan(stage=stage, i_rated=i_rated, theta_re=theta_re)


def generate_fem_export_procedure(**kwargs: Any) -> dict[str, Any]:
    return scriptenv_workflow.fem_export_procedure(**kwargs)


def resume_fem_export(output: str) -> dict[str, Any]:
    return scriptenv_workflow.parse_prefixed_json(output)


def fem_export_status(job_id: str = "fem_export_smoke", out: str = "data/flux_map_fem.csv") -> dict[str, Any]:
    return scriptenv_workflow.fem_export_status(job_id=job_id, out=out)


def generate_pyaedt_launch_owned_probe(
    port: int = 50052,
    job_id: str = "pyaedt_launch_probe",
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    return pyaedt_workflow.launch_owned_probe_procedure(
        port=port,
        job_id=job_id,
        timeout_seconds=timeout_seconds,
    )


def resume_pyaedt_launch_owned_probe(output: str) -> dict[str, Any]:
    return pyaedt_workflow.parse_prefixed_json(output)


def generate_pyaedt_project_probe_procedure(
    project: str,
    port: int = 50052,
    job_id: str = "pyaedt_project_probe",
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    return pyaedt_workflow.project_probe_procedure(
        project=project,
        port=port,
        job_id=job_id,
        timeout_seconds=timeout_seconds,
    )


def resume_pyaedt_project_probe(output: str) -> dict[str, Any]:
    return pyaedt_workflow.parse_prefixed_json(output)


def generate_pyaedt_fem_export_procedure(**kwargs: Any) -> dict[str, Any]:
    return pyaedt_workflow.fem_export_procedure(**kwargs)


def resume_pyaedt_fem_export(output: str) -> dict[str, Any]:
    return pyaedt_workflow.parse_prefixed_json(output)


def pyaedt_export_status(job_id: str = "pyaedt_fem_export_smoke", out: str = "data/flux_map_fem.csv") -> dict[str, Any]:
    return pyaedt_workflow.export_status(job_id=job_id, out=out)


def generate_aedt_process_inventory() -> dict[str, Any]:
    return pyaedt_workflow.process_inventory_procedure()


def generate_stop_duplicate_aedt_procedure(keep_pid: int | None = None) -> dict[str, Any]:
    return pyaedt_workflow.stop_duplicate_aedt_procedure(keep_pid=keep_pid)


def resume_process_cleanup(output: str) -> dict[str, Any]:
    category = policy.classify_failure_text(output)
    stopped = sorted({int(pid) for pid in re.findall(r"Stopped AEDT PID\s+(\d+)", output)})
    return {
        "status": "ok",
        "classification": {"category": category, "known_categories": policy.FAILURE_CATEGORIES},
        "stopped_pids": stopped,
        "recommended_next_step": "generate_aedt_process_inventory" if stopped else "inspect_process_inventory_output",
    }


def write_procedure(procedure: dict[str, Any], filename: str | None = None) -> dict[str, Any]:
    if procedure.get("status") != "user_action_required":
        raise ValueError("procedure must be a user_action_required response")
    procedure_id = str(procedure.get("procedure_id", "procedure"))
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename or f"{procedure_id}.md")
    out_dir = policy.PROJECT_ROOT / "docs" / "procedures"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / safe_name
    out_path.write_text(procedures.render_markdown(procedure), encoding="utf-8")
    return {"status": "ok", "path": str(out_path), "relative_path": _relative(out_path)}


def resume_from_user_output(output: str) -> dict[str, Any]:
    category = policy.classify_failure_text(output)
    ports = sorted({int(port) for port in re.findall(r"GRPC server running on port:\s*(\d+)", output)})
    lowered = output.lower()
    scriptenv_success = "2025.2.0" in output or "scriptenv" in lowered and "getversion" in lowered
    if scriptenv_success and category == "pyaedt_attach":
        next_step = "use_scriptenv_workflow_pyaedt_blocked"
    elif scriptenv_success:
        next_step = "use_scriptenv_workflow"
    elif ports:
        next_step = "run_attach_test_procedure"
    elif category in {"pyaedt_attach", "grpc_transport", "port_conflict"}:
        next_step = "try_raw_scriptenv_attach_or_new_port"
    elif category == "license":
        next_step = "manual_aedt_gui_license_check"
    elif category in {"filesystem_permission", "aedt_config"}:
        next_step = "inspect_workspace_config_and_logs"
    else:
        next_step = "generate_launch_procedure"
    return {
        "status": "ok",
        "classification": {"category": category, "known_categories": policy.FAILURE_CATEGORIES},
        "parsed_ports": ports,
        "recommended_next_step": next_step,
    }
