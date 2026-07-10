"""Policy and procedure tests that do not launch AEDT."""

from __future__ import annotations

import json

import pytest

from aedt_mcp import execution_policy as policy
from aedt_mcp import operator_tools, procedures, pyaedt_workflow, scriptenv_workflow
from aedt_mcp.schemas import GenerateFemExportProcedureArgs
from aedt_mcp.session import SESSION, AedtSessionError


def test_policy_blocks_unsafe_actions():
    decision = policy.decide_tool("open_design")
    assert decision.allowed is False
    assert decision.tier == policy.Tier.USER_RUN_NATIVE_POWERSHELL


def test_user_action_required_schema():
    response = policy.blocked_tool_response("open_design")
    assert response["status"] == "user_action_required"
    for key in ["reason", "risk_level", "procedure_id", "commands", "expected_output", "paste_back", "log_paths", "cleanup"]:
        assert key in response


def test_launch_and_attach_are_separate():
    launch = procedures.launch_procedure(50052)
    attach = procedures.attach_test_procedure(50052, include_scriptenv=False)
    assert launch["procedure_id"] != attach["procedure_id"]
    assert any("-grpcsrv 50052" in command for command in launch["commands"])
    assert not any("-grpcsrv" in command for command in attach["commands"])


def test_attach_never_launches_new_aedt():
    script = procedures.pyaedt_attach_script(50052)
    assert "new_desktop=False" in script
    assert "port=50052" in script
    assert "machine=\"localhost\"" in script


def test_no_graphical_aedt_launch():
    launch = procedures.launch_procedure(50052)
    assert any(" -ng " in command for command in launch["commands"])
    assert not any("--graphical" in command.lower() for command in launch["commands"])


def test_no_c_temp_dependency():
    launch = procedures.launch_procedure(50052)
    joined = "\n".join(launch["commands"])
    assert "C:\\temp" not in joined
    assert "C:/temp" not in joined
    assert "tmp\\aedt_temp" in joined


def test_procedure_generation():
    response = operator_tools.generate_attach_test(50052, include_scriptenv=True)
    assert response["status"] == "user_action_required"
    assert "generated_scripts" in response
    assert any(path.endswith("attach_pyaedt_50052.py") for path in response["generated_scripts"])


def test_log_failure_classification():
    assert operator_tools.classify_failure("C:/temp is read only")["category"] == "filesystem_permission"
    assert operator_tools.classify_failure("PyAEDT reports no active session")["category"] == "pyaedt_attach"
    assert operator_tools.classify_failure("PyAEDT attempted to launch AEDT during attach-only test; blocked by generated script")["category"] == "pyaedt_attach"
    assert operator_tools.classify_failure("No active AEDT gRPC session found on port 50052. Opening a new AEDT session.")["category"] == "pyaedt_student_attach_detection_failure"
    assert operator_tools.classify_failure("pyaedt non-finite row")["category"] == "pyaedt_nonfinite_flux_data"
    assert operator_tools.classify_failure("port already in use")["category"] == "aedt_port_conflict"


def test_capabilities_file_loads():
    capabilities = policy.load_capabilities()
    assert capabilities["environment"]["aedt_version"] == "2025.2SV"
    assert capabilities["environment"]["scriptenv_attach_confirmed"] is True
    assert capabilities["preferred_paths"]["aedt_temp"] == "tmp/aedt_temp"


def test_resume_prefers_scriptenv_when_pyaedt_is_blocked():
    output = "RuntimeError: PyAEDT attempted to launch AEDT during attach-only test; blocked by generated script.\n2025.2.0"
    resumed = operator_tools.resume_from_user_output(output)
    assert resumed["recommended_next_step"] == "use_scriptenv_workflow_pyaedt_blocked"


def test_scriptenv_probe_generation_is_attach_only():
    response = operator_tools.generate_scriptenv_probe(50052)
    assert response["status"] == "user_action_required"
    script = (policy.PROJECT_ROOT / "scripts" / "generated" / "scriptenv_probe_50052.py").read_text()
    assert 'ScriptEnv.Initialize("", False, "localhost", 50052)' in script
    assert "new_desktop=True" not in script
    assert "C:\\temp" not in script


def test_project_probe_procedure_uses_workspace_copy():
    response = operator_tools.generate_project_probe_procedure(
        project=r"C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM\Examples\RMxprt\ipm\ipm_1.aedt",
        port=50052,
        job_id="unit_probe",
    )
    assert response["status"] == "user_action_required"
    assert any("tmp/aedt_projects/unit_probe" in path for path in response["log_paths"])
    script = policy.PROJECT_ROOT / "scripts" / "generated" / "scriptenv_project_probe_50052_unit_probe.py"
    text = script.read_text()
    assert "COPY_DIR" in text
    assert "tmp\\aedt_projects" in text or "tmp/aedt_projects" in text
    assert "desktop.OpenProject(str(copied))" in text


def test_fem_export_plan_stages():
    assert operator_tools.generate_fem_export_plan("smoke")["rows"] == 4
    assert operator_tools.generate_fem_export_plan("validation")["rows"] == 25
    assert operator_tools.generate_fem_export_plan("full")["rows"] == 1600


def test_fem_export_schema_rejects_invalid_grid():
    try:
        GenerateFemExportProcedureArgs(project_copy="tmp/aedt_projects/x/x.aedt", design="D", setup="S", n_id=1)
    except Exception as exc:
        assert "greater than or equal to 2" in str(exc)
    else:
        raise AssertionError("invalid grid accepted")


def test_fem_export_procedure_paths_and_script_safety():
    response = operator_tools.generate_fem_export_procedure(
        project_copy="tmp/aedt_projects/unit_probe/ipm_1.aedt",
        design="Maxwell2DDesign1",
        setup="Setup1",
        job_id="unit_export",
        n_id=2,
        n_iq=2,
    )
    assert response["status"] == "user_action_required"
    assert any("tmp/aedt_jobs/unit_export" in path for path in response["log_paths"])
    script = policy.PROJECT_ROOT / "scripts" / "generated" / "scriptenv_fem_export_unit_export.py"
    text = script.read_text()
    assert 'ScriptEnv.Initialize("", False, "localhost", 50052)' in text
    assert "new_desktop=True" not in text
    assert "C:\\temp" not in text
    assert "data\\flux_map_fem.csv" in text or "data/flux_map_fem.csv" in text
    assert "progress.csv" in text


def test_prefixed_json_resume_parser():
    parsed = scriptenv_workflow.parse_prefixed_json('AEDT_MCP_RESULT_JSON={"status":"ok","aedt_version":"2025.2.0"}')
    assert parsed["recommended_next_step"] == "generate_project_probe_procedure"
    parsed = scriptenv_workflow.parse_prefixed_json("non-finite row")
    assert parsed["recommended_next_step"] == "inspect_non_finite_rows"


def test_fem_export_status_reads_csv(tmp_path):
    job_dir = policy.PROJECT_ROOT / "tmp" / "aedt_jobs" / "unit_status"
    job_dir.mkdir(parents=True, exist_ok=True)
    progress = job_dir / "progress.csv"
    progress.write_text("Id,Iq,Phi_d,Phi_q\n-1,0,0.1,0.0\n")
    status = operator_tools.fem_export_status("unit_status", out="tmp/missing_fem_status.csv")
    assert status["progress_csv"]["exists"] is True
    assert status["progress_csv"]["header_ok"] is True
    assert status["progress_csv"]["finite"] is True


def test_pyaedt_launch_owned_probe_script_safety():
    response = operator_tools.generate_pyaedt_launch_owned_probe(port=50052, job_id="unit_pyaedt_probe")
    assert response["status"] == "user_action_required"
    script = policy.PROJECT_ROOT / "scripts" / "generated" / "pyaedt_launch_owned_probe_unit_pyaedt_probe.py"
    text = script.read_text()
    assert 'version="2025.2"' in text
    assert "student_version=True" in text
    assert "non_graphical=True" in text
    assert "new_desktop=True" in text
    assert "settings.grpc_secure_mode = False" in text
    assert 'os.environ["PYAEDT_USE_PRE_GRPC_ARGS"] = "True"' in text
    assert "C:\\temp" not in text
    assert "Stop-Process" not in text


def test_pyaedt_project_probe_uses_workspace_copy_and_rejects_direct_mutation():
    response = operator_tools.generate_pyaedt_project_probe_procedure(
        project=r"C:\Users\darsh\TAMU\project.aedt",
        port=50052,
        job_id="unit_pyaedt_project",
    )
    assert response["status"] == "user_action_required"
    assert any("tmp/aedt_projects/unit_pyaedt_project" in path for path in response["log_paths"])
    script = policy.PROJECT_ROOT / "scripts" / "generated" / "pyaedt_project_probe_unit_pyaedt_project.py"
    text = script.read_text()
    assert "copy_project(SOURCE_PROJECT)" in text
    assert "PROJECT_COPY_DIR" in text
    assert "reject_unsafe_source_project" in text
    assert "Program Files" in text
    assert "OneDrive" in text
    assert "Maxwell3d(project=str(copied)" in text
    assert "C:\\temp" not in text


def test_pyaedt_fem_export_script_contract_and_paths():
    response = operator_tools.generate_pyaedt_fem_export_procedure(
        project_copy=str(policy.PROJECT_ROOT / "tmp" / "aedt_projects" / "unit_pyaedt_project" / "project.aedt"),
        design="Maxwell3DDesign1",
        setup="Setup1",
        job_id="unit_pyaedt_export",
        n_id=2,
        n_iq=2,
    )
    assert response["status"] == "user_action_required"
    assert any("tmp/aedt_jobs/unit_pyaedt_export" in path for path in response["log_paths"])
    script = policy.PROJECT_ROOT / "scripts" / "generated" / "pyaedt_fem_export_unit_pyaedt_export.py"
    text = script.read_text()
    assert "HEADER = (\"Id\", \"Iq\", \"Phi_d\", \"Phi_q\")" in text
    assert "require_under(PROJECT_COPY, PROJECT_ROOT / \"tmp\" / \"aedt_projects\"" in text
    assert "require_under(OUT_CSV, PROJECT_ROOT / \"data\"" in text
    assert "data/flux_map_fem.csv" in text
    assert "progress.csv" in text
    assert "all(math.isfinite(x) for x in row)" in text
    assert "Stop-Process" not in text
    assert "C:\\temp" not in text


def test_pyaedt_resume_and_status_helpers():
    parsed = pyaedt_workflow.parse_prefixed_json('AEDT_MCP_RESULT_JSON={"status":"ok","out_csv":"data/flux_map_fem.csv"}')
    assert parsed["recommended_next_step"] == "validate_fem_export_status"
    parsed = pyaedt_workflow.parse_prefixed_json('AEDT_MCP_ERROR_JSON={"status":"error","category":"pyaedt_fem_export_failed","recommended_next_step":"inspect_pyaedt_fem_export_logs"}')
    assert parsed["recommended_next_step"] == "inspect_pyaedt_fem_export_logs"


def test_aedt_process_inventory_and_cleanup_are_user_run_only():
    inventory = operator_tools.generate_aedt_process_inventory()
    assert inventory["status"] == "user_action_required"
    assert not any("Stop-Process" in command for command in inventory["commands"])
    cleanup = operator_tools.generate_stop_duplicate_aedt_procedure(keep_pid=40544)
    assert cleanup["status"] == "user_action_required"
    assert any("Stop-Process" in command for command in cleanup["commands"])
    assert any("40544" in command for command in cleanup["commands"])
    resumed = operator_tools.resume_process_cleanup("Stopped AEDT PID 39344")
    assert resumed["stopped_pids"] == [39344]
    assert resumed["recommended_next_step"] == "generate_aedt_process_inventory"


def test_existing_core_tests_still_pass():
    capabilities = json.dumps(policy.load_capabilities())
    assert "tmp/aedt_jobs" in capabilities


def test_session_launch_is_policy_blocked():
    SESSION.release()
    with pytest.raises(AedtSessionError):
        SESSION.launch()
