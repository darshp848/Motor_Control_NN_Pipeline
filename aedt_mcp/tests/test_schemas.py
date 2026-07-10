"""Pytest suite: schema validation, server registration, and error handling.

These tests do NOT launch AEDT - they exercise pure-Python code paths so they
can run in CI without a license.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from aedt_mcp.schemas import (
    CreateBoxArgs,
    CreatePolylineArgs,
    CreateSetupArgs,
    OpenDesignArgs,
    RunDesignVectorArgs,
)
from aedt_mcp.server import server

# ----------------------------------------------------------- schema validation

def test_open_design_valid():
    a = OpenDesignArgs(design_type="maxwell3d", project="motor", design="rotor_a")
    assert a.design_type == "maxwell3d"
    assert a.project == "motor"


def test_open_design_invalid_type():
    with pytest.raises(ValidationError):
        OpenDesignArgs(design_type="icepak")


def test_create_box_accepts_any_position_type():
    # pydantic doesn't enforce list length here; the tool handler validates at runtime.
    a = CreateBoxArgs(position=[0, 0], sizes=[1, 1, 1])
    assert a.position == [0, 0]


def test_create_box_tool_rejects_wrong_length():
    from aedt_mcp.pyansys_api import ToolError
    from aedt_mcp.tools.modeler import create_box

    args = CreateBoxArgs(position=[0, 0], sizes=[1, 1, 1])
    with pytest.raises(ToolError):
        create_box(args)


def test_create_polyline_accepts_multiple_point_groups():
    a = CreatePolylineArgs(points=[0, 0, 0, 1, 1, 1])
    assert len(a.points) == 6


def test_create_polyline_rejects_bad_count():
    with pytest.raises(ValidationError):
        CreatePolylineArgs(points=[0, 0, 0, 1])


def test_create_setup_defaults_maxwell_transient():
    a = CreateSetupArgs(design_type="maxwell3d", setup_type="Transient",
                        stop_time="10ms", time_step="0.5ms")
    assert a.max_passes == 10
    assert a.save_fields is True


def test_run_design_vector_requires_expressions():
    with pytest.raises(ValidationError):
        RunDesignVectorArgs(design_type="maxwell3d",
                            variables={"i": "1A"})  # missing expressions


# --------------------------------------------------------- server registration

def _list_tools():
    return asyncio.run(server.list_tools())


def test_server_exposes_expected_tools():
    tools = _list_tools()
    names = {t.name for t in tools}
    expected = {
        "aedt.safe_status", "aedt.diagnose_environment", "aedt.parse_logs",
        "aedt.classify_failure", "aedt.generate_launch_procedure",
        "aedt.generate_attach_test", "aedt.write_procedure",
        "aedt.resume_from_user_output", "aedt.generate_scriptenv_probe",
        "aedt.resume_scriptenv_probe", "aedt.generate_project_probe_procedure",
        "aedt.resume_project_probe", "aedt.generate_fem_export_plan",
        "aedt.generate_fem_export_procedure", "aedt.resume_fem_export",
        "aedt.fem_export_status", "aedt.generate_pyaedt_launch_owned_probe",
        "aedt.resume_pyaedt_launch_owned_probe",
        "aedt.generate_pyaedt_project_probe_procedure",
        "aedt.resume_pyaedt_project_probe",
        "aedt.generate_pyaedt_fem_export_procedure",
        "aedt.resume_pyaedt_fem_export", "aedt.pyaedt_export_status",
        "aedt.generate_aedt_process_inventory",
        "aedt.generate_stop_duplicate_aedt_procedure",
        "aedt.resume_process_cleanup",
        "open_design", "create_box", "create_cylinder", "create_polyline",
        "duplicate_around_axis", "assign_material", "set_variable",
        "create_coil", "create_winding", "assign_rotate_motion",
        "assign_length_mesh", "create_setup", "analyze_setup",
        "get_solution_data", "get_torque", "get_flux_linkage",
        "create_parametric_setup", "get_field_points_on_contour",
        "run_design_vector", "save_project", "close_project", "list_designs",
    }
    missing = expected - names
    assert not missing, f"missing tools: {missing}"
    assert len(tools) == 73


def test_tools_have_input_schema():
    tools = _list_tools()
    for t in tools:
        s = t.inputSchema
        assert isinstance(s, dict), f"{t.name}: inputSchema is not a dict"
        assert s.get("type") == "object", f"{t.name}: schema not object"


# ---------------------------------------------------------- error-handling wrapper

def test_handle_errors_wraps_unexpected_exception():
    from aedt_mcp.pyansys_api import ToolError, handle_errors

    @handle_errors
    def boom():
        raise RuntimeError("kaboom")

    with pytest.raises(ToolError) as exc_info:
        boom()
    assert "kaboom" in str(exc_info.value)
    assert "traceback" in exc_info.value.details


def test_handle_errors_passes_through_tool_error():
    from aedt_mcp.pyansys_api import ToolError, handle_errors

    @handle_errors
    def fail():
        raise ToolError(message="intentional")

    with pytest.raises(ToolError) as exc_info:
        fail()
    assert exc_info.value.message == "intentional"
