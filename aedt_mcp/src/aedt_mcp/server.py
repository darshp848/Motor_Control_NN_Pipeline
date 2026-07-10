"""FastMCP server: registers all pyaedt-backed tools and runs stdio transport.

Each tool function takes a single pydantic model argument whose JSON Schema
becomes the MCP `inputSchema`. Return values are JSON-serialisable dicts;
fastmcp wraps them as TextContent.
"""

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import execution_policy as policy
from . import operator_tools as opt
from . import tools  # noqa: F401  (registers handlers below)
from .schemas import (
    AddMaterialArgs,
    AddVariationArgs,
    AnalyzeParametricArgs,
    AnalyzeSetupArgs,
    AssignCurrentArgs,
    AssignLengthMeshArgs,
    AssignMagnetizationArgs,
    AssignMaterialArgs,
    AssignRotateMotionArgs,
    AssignSkinDepthMeshArgs,
    AssignVoltageArgs,
    BooleanArgs,
    ClassifyFailureArgs,
    CloseProjectArgs,
    CreateBoundaryDependentArgs,
    CreateBoxArgs,
    CreateCircleArgs,
    CreateCoilArgs,
    CreateCylinderArgs,
    CreateParametricSetupArgs,
    CreatePolylineArgs,
    CreateRectangleArgs,
    CreateSetupArgs,
    CreateWindingArgs,
    DeleteSetupArgs,
    DiagnoseEnvironmentArgs,
    DuplicateAlongLineArgs,
    DuplicateAroundAxisArgs,
    EditSetupArgs,
    ExportFieldVolumeArgs,
    FemExportStatusArgs,
    FieldCalculatorEvalArgs,
    GenerateAedtProcessInventoryArgs,
    GenerateAttachTestArgs,
    GenerateFemExportPlanArgs,
    GenerateFemExportProcedureArgs,
    GenerateLaunchProcedureArgs,
    GenerateProjectProbeProcedureArgs,
    GeneratePyAedtFemExportProcedureArgs,
    GeneratePyAedtLaunchOwnedProbeArgs,
    GeneratePyAedtProjectProbeProcedureArgs,
    GenerateScriptEnvProbeArgs,
    GenerateStopDuplicateAedtProcedureArgs,
    GetFieldPointsOnContourArgs,
    GetFluxLinkageArgs,
    GetSolutionDataArgs,
    GetSolveStatusArgs,
    GetTorqueArgs,
    GetVariationTableArgs,
    GetWindingInductanceArgs,
    ImportGeometryArgs,
    ListDesignsArgs,
    ListMaterialsArgs,
    ListVariablesArgs,
    MoveTranslateArgs,
    OpenDesignArgs,
    ParseLogsArgs,
    PyAedtExportStatusArgs,
    ResumeFemExportArgs,
    ResumeFromUserOutputArgs,
    ResumeProcessCleanupArgs,
    ResumeProjectProbeArgs,
    ResumePyAedtFemExportArgs,
    ResumePyAedtLaunchOwnedProbeArgs,
    ResumePyAedtProjectProbeArgs,
    ResumeScriptEnvProbeArgs,
    RotateArgs,
    RunDesignVectorArgs,
    SafeStatusArgs,
    SaveProjectArgs,
    SetVariableArgs,
    SurfaceMeshArgs,
    WriteProcedureArgs,
)
from .tools import (
    boundaries_excitations as bne,
)
from .tools import (
    fields as fld,
)
from .tools import (
    materials as mat,
)
from .tools import (
    mesh as msh,
)
from .tools import (
    modeler as mdl,
)
from .tools import (
    nn_loop as nnl,
)
from .tools import (
    parametric as prm,
)
from .tools import (
    project_design as pdg,
)
from .tools import (
    results as res,
)
from .tools import (
    setup as sup,
)
from .tools import (
    solve as slv,
)
from .tools import (
    variables as var,
)

logger = logging.getLogger("aedt_mcp")

server = FastMCP(
    name="aedt-mcp",
    instructions=(
        "Exposed PyAnsys (AEDT 2025R2 Student) for motor FEM + NN data. "
        "Active design types: hfss, maxwell3d. Numeric datasets are written "
        "under ./out; tool responses carry absolute paths plus summary JSON."
    ),
    dependencies=["mcp>=1.2.0", "pyaedt>=1.0.0", "pydantic>=2.5", "numpy>=1.26"],
)


# Register each tool with the FastMCP server. The docstring of the inner
# function becomes the tool description sent to the LLM.
def _register(name: str, handler: Any, arg_cls: Any, description: str) -> None:
    def _tool(args: arg_cls) -> Any:  # type: ignore[valid-type]
        decision = policy.decide_tool(name)
        if not decision.allowed:
            return policy.blocked_tool_response(name)
        return handler(args)

    _tool.__doc__ = description
    _tool.__name__ = name
    server.tool(name=name, description=description)(_tool)


def _safe_status(_args: SafeStatusArgs) -> dict[str, Any]:
    return opt.safe_status()


def _diagnose_environment(_args: DiagnoseEnvironmentArgs) -> dict[str, Any]:
    return opt.diagnose_environment()


def _parse_logs(args: ParseLogsArgs) -> dict[str, Any]:
    return opt.parse_logs(log_dir=args.log_dir, max_matches=args.max_matches)


def _classify_failure(args: ClassifyFailureArgs) -> dict[str, Any]:
    return opt.classify_failure(args.text)


def _generate_launch_procedure(args: GenerateLaunchProcedureArgs) -> dict[str, Any]:
    return opt.generate_launch_procedure(args.port)


def _generate_attach_test(args: GenerateAttachTestArgs) -> dict[str, Any]:
    return opt.generate_attach_test(args.port, args.include_scriptenv)


def _write_procedure(args: WriteProcedureArgs) -> dict[str, Any]:
    return opt.write_procedure(args.procedure, args.filename)


def _resume_from_user_output(args: ResumeFromUserOutputArgs) -> dict[str, Any]:
    return opt.resume_from_user_output(args.output)


def _generate_scriptenv_probe(args: GenerateScriptEnvProbeArgs) -> dict[str, Any]:
    return opt.generate_scriptenv_probe(args.port, args.timeout_seconds)


def _resume_scriptenv_probe(args: ResumeScriptEnvProbeArgs) -> dict[str, Any]:
    return opt.resume_scriptenv_probe(args.output)


def _generate_project_probe_procedure(args: GenerateProjectProbeProcedureArgs) -> dict[str, Any]:
    return opt.generate_project_probe_procedure(
        project=args.project,
        port=args.port,
        job_id=args.job_id,
        timeout_seconds=args.timeout_seconds,
    )


def _resume_project_probe(args: ResumeProjectProbeArgs) -> dict[str, Any]:
    return opt.resume_project_probe(args.output)


def _generate_fem_export_plan(args: GenerateFemExportPlanArgs) -> dict[str, Any]:
    return opt.generate_fem_export_plan(args.stage, args.i_rated, args.theta_re)


def _generate_fem_export_procedure(args: GenerateFemExportProcedureArgs) -> dict[str, Any]:
    return opt.generate_fem_export_procedure(**args.model_dump())


def _resume_fem_export(args: ResumeFemExportArgs) -> dict[str, Any]:
    return opt.resume_fem_export(args.output)


def _fem_export_status(args: FemExportStatusArgs) -> dict[str, Any]:
    return opt.fem_export_status(args.job_id, args.out)


def _generate_pyaedt_launch_owned_probe(args: GeneratePyAedtLaunchOwnedProbeArgs) -> dict[str, Any]:
    return opt.generate_pyaedt_launch_owned_probe(args.port, args.job_id, args.timeout_seconds)


def _resume_pyaedt_launch_owned_probe(args: ResumePyAedtLaunchOwnedProbeArgs) -> dict[str, Any]:
    return opt.resume_pyaedt_launch_owned_probe(args.output)


def _generate_pyaedt_project_probe_procedure(args: GeneratePyAedtProjectProbeProcedureArgs) -> dict[str, Any]:
    return opt.generate_pyaedt_project_probe_procedure(
        project=args.project,
        port=args.port,
        job_id=args.job_id,
        timeout_seconds=args.timeout_seconds,
    )


def _resume_pyaedt_project_probe(args: ResumePyAedtProjectProbeArgs) -> dict[str, Any]:
    return opt.resume_pyaedt_project_probe(args.output)


def _generate_pyaedt_fem_export_procedure(args: GeneratePyAedtFemExportProcedureArgs) -> dict[str, Any]:
    return opt.generate_pyaedt_fem_export_procedure(**args.model_dump())


def _resume_pyaedt_fem_export(args: ResumePyAedtFemExportArgs) -> dict[str, Any]:
    return opt.resume_pyaedt_fem_export(args.output)


def _pyaedt_export_status(args: PyAedtExportStatusArgs) -> dict[str, Any]:
    return opt.pyaedt_export_status(args.job_id, args.out)


def _generate_aedt_process_inventory(_args: GenerateAedtProcessInventoryArgs) -> dict[str, Any]:
    return opt.generate_aedt_process_inventory()


def _generate_stop_duplicate_aedt_procedure(args: GenerateStopDuplicateAedtProcedureArgs) -> dict[str, Any]:
    return opt.generate_stop_duplicate_aedt_procedure(args.keep_pid)


def _resume_process_cleanup(args: ResumeProcessCleanupArgs) -> dict[str, Any]:
    return opt.resume_process_cleanup(args.output)


# ---- safe operator guidance ----
_register("aedt.safe_status", _safe_status, SafeStatusArgs,
          "Report known AEDT/Codex state without launching AEDT.")
_register("aedt.diagnose_environment", _diagnose_environment, DiagnoseEnvironmentArgs,
          "Check workspace-local paths, copied config, logs, and known limits.")
_register("aedt.parse_logs", _parse_logs, ParseLogsArgs,
          "Parse workspace-local AEDT logs for known failure signatures.")
_register("aedt.classify_failure", _classify_failure, ClassifyFailureArgs,
          "Classify pasted AEDT/PyAEDT output into a known failure category.")
_register("aedt.generate_launch_procedure", _generate_launch_procedure, GenerateLaunchProcedureArgs,
          "Generate native PowerShell instructions to launch AEDT gRPC manually.")
_register("aedt.generate_attach_test", _generate_attach_test, GenerateAttachTestArgs,
          "Generate PyAEDT and ScriptEnv attach tests that never launch a new AEDT instance.")
_register("aedt.write_procedure", _write_procedure, WriteProcedureArgs,
          "Write a numbered user-run procedure to docs/procedures.")
_register("aedt.resume_from_user_output", _resume_from_user_output, ResumeFromUserOutputArgs,
          "Parse pasted PowerShell output and recommend the next operator-guided step.")
_register("aedt.generate_scriptenv_probe", _generate_scriptenv_probe, GenerateScriptEnvProbeArgs,
          "Generate a native PowerShell ScriptEnv attach probe for an existing AEDT gRPC server.")
_register("aedt.resume_scriptenv_probe", _resume_scriptenv_probe, ResumeScriptEnvProbeArgs,
          "Parse ScriptEnv probe output and recommend the next step.")
_register("aedt.generate_project_probe_procedure", _generate_project_probe_procedure, GenerateProjectProbeProcedureArgs,
          "Generate a ScriptEnv project metadata probe that opens only a workspace copy.")
_register("aedt.resume_project_probe", _resume_project_probe, ResumeProjectProbeArgs,
          "Parse ScriptEnv project probe output and recommend design/setup selection.")
_register("aedt.generate_fem_export_plan", _generate_fem_export_plan, GenerateFemExportPlanArgs,
          "Return the staged FEM export grid plan for smoke, validation, or full data generation.")
_register("aedt.generate_fem_export_procedure", _generate_fem_export_procedure, GenerateFemExportProcedureArgs,
          "Generate a user-run ScriptEnv FEM export procedure that writes progress and final CSV.")
_register("aedt.resume_fem_export", _resume_fem_export, ResumeFemExportArgs,
          "Parse ScriptEnv FEM export output and recommend the next step.")
_register("aedt.fem_export_status", _fem_export_status, FemExportStatusArgs,
          "Inspect workspace-local FEM export progress and final CSV status.")
_register("aedt.generate_pyaedt_launch_owned_probe", _generate_pyaedt_launch_owned_probe, GeneratePyAedtLaunchOwnedProbeArgs,
          "Generate a user-run PyAEDT launch-owned AEDT 2025 R2 Student probe.")
_register("aedt.resume_pyaedt_launch_owned_probe", _resume_pyaedt_launch_owned_probe, ResumePyAedtLaunchOwnedProbeArgs,
          "Parse PyAEDT launch-owned probe output and recommend the next step.")
_register("aedt.generate_pyaedt_project_probe_procedure", _generate_pyaedt_project_probe_procedure, GeneratePyAedtProjectProbeProcedureArgs,
          "Generate a user-run PyAEDT project metadata probe that opens only a workspace copy.")
_register("aedt.resume_pyaedt_project_probe", _resume_pyaedt_project_probe, ResumePyAedtProjectProbeArgs,
          "Parse PyAEDT project probe output and recommend design/setup selection.")
_register("aedt.generate_pyaedt_fem_export_procedure", _generate_pyaedt_fem_export_procedure, GeneratePyAedtFemExportProcedureArgs,
          "Generate a user-run PyAEDT launch-owned FEM export procedure with progress and final CSV validation.")
_register("aedt.resume_pyaedt_fem_export", _resume_pyaedt_fem_export, ResumePyAedtFemExportArgs,
          "Parse PyAEDT FEM export output and recommend the next step.")
_register("aedt.pyaedt_export_status", _pyaedt_export_status, PyAedtExportStatusArgs,
          "Inspect workspace-local PyAEDT FEM export progress and final CSV status.")
_register("aedt.generate_aedt_process_inventory", _generate_aedt_process_inventory, GenerateAedtProcessInventoryArgs,
          "Generate a user-run PowerShell process and port inventory for AEDT/PyAEDT debugging.")
_register("aedt.generate_stop_duplicate_aedt_procedure", _generate_stop_duplicate_aedt_procedure, GenerateStopDuplicateAedtProcedureArgs,
          "Generate a user-run PowerShell procedure to stop duplicate AEDT processes.")
_register("aedt.resume_process_cleanup", _resume_process_cleanup, ResumeProcessCleanupArgs,
          "Parse user-run AEDT process cleanup output and recommend the next step.")


# ---- project / design ----
_register("open_design", pdg.open_design, OpenDesignArgs,
          "Open or create an AEDT project/design of type 'hfss' or 'maxwell3d' and mark it active.")
_register("list_designs", pdg.list_designs, ListDesignsArgs,
          "List designs currently registered with the MCP server.")
_register("save_project", pdg.save_project, SaveProjectArgs,
          "Save the active project (optionally to a full path).")
_register("close_project", pdg.close_project, CloseProjectArgs,
          "Close a project, releasing its registered design clients.")

# ---- modeler ----
_register("create_box", mdl.create_box, CreateBoxArgs,
          "Create a 3D box at position with sizes; optional material assignment.")
_register("create_cylinder", mdl.create_cylinder, CreateCylinderArgs,
          "Create a 3D cylinder about an axis; optional material assignment.")
_register("create_circle", mdl.create_circle, CreateCircleArgs,
          "Create a 2D circle on a plane (sheet body).")
_register("create_rectangle", mdl.create_rectangle, CreateRectangleArgs,
          "Create a 2D rectangle on a plane.")
_register("create_polyline", mdl.create_polyline, CreatePolylineArgs,
          "Create a polyline (path) from a flat [x,y,z,...] list; optionally close it.")
_register("boolean_op", mdl.boolean_op, BooleanArgs,
          "Boolean unite/intersect/subtract on solid bodies.")
_register("duplicate_around_axis", mdl.duplicate_around_axis, DuplicateAroundAxisArgs,
          "Duplicate an object around an axis - good for rotor/stator pole patterns.")
_register("duplicate_along_line", mdl.duplicate_along_line, DuplicateAlongLineArgs,
          "Duplicate an object along a translation vector.")
_register("move_translate", mdl.move_translate, MoveTranslateArgs,
          "Translate objects by a vector (model units, typically meter).")
_register("rotate", mdl.rotate, RotateArgs,
          "Rotate objects about an axis by a given angle in degrees.")
_register("import_geometry", mdl.import_geometry, ImportGeometryArgs,
          "Import a STEP/IGES 3D CAD file into the active design.")

# ---- materials ----
_register("add_material", mat.add_material, AddMaterialArgs,
          "Add a custom material to the active design's material library.")
_register("assign_material", mat.assign_material, AssignMaterialArgs,
          "Assign a material to one or more named objects.")
_register("list_materials", mat.list_materials, ListMaterialsArgs,
          "List materials available to the active design.")

# ---- variables ----
_register("set_variable", var.set_variable, SetVariableArgs,
          "Set a design or project ($-prefixed) variable to a value/expression.")
_register("list_variables", var.list_variables, ListVariablesArgs,
          "List design and project variables for the active design.")

# ---- boundaries / excitations ----
_register("create_coil", bne.create_coil, CreateCoilArgs,
          "Assign a Maxwell coil terminal to a conductor object (rotating machine winding).")
_register("create_winding", bne.create_winding, CreateWindingArgs,
          "Create a winding (current/voltage source) and attach one or more coils.")
_register("assign_current", bne.assign_current, AssignCurrentArgs,
          "Apply a current excitation to the chosen objects.")
_register("assign_voltage", bne.assign_voltage, AssignVoltageArgs,
          "Apply a voltage excitation to the chosen objects.")
_register("assign_magnetization", bne.assign_magnetization, AssignMagnetizationArgs,
          "Configure magnetisation of a permanent-magnet object (magnitude + direction vector).")
_register("assign_rotate_motion", bne.assign_rotate_motion, AssignRotateMotionArgs,
          "Assign rotational motion to the rotor band region. CRITICAL for rotating machines.")
_register("create_boundary_dependent", bne.create_boundary_dependent, CreateBoundaryDependentArgs,
          "Create master/dependent (symmetry) boundary on a set of faces.")

# ---- mesh ----
_register("assign_length_mesh", msh.assign_length_mesh, AssignLengthMeshArgs,
          "Length-based mesh refinement on selected objects.")
_register("assign_skin_depth_mesh", msh.assign_skin_depth_mesh, AssignSkinDepthMeshArgs,
          "Skin-depth mesh (for eddy-current / transient conductors).")
_register("surface_mesh", msh.surface_mesh, SurfaceMeshArgs,
          "Limit number of elements on selected faces.")

# ---- setup ----
_register("create_setup", sup.create_setup, CreateSetupArgs,
          "Create an analysis setup (Maxwell: Magnetostatic/Transient/EddyCurrent; HFSS: HFSSDrivenDefault).")
_register("edit_setup", sup.edit_setup, EditSetupArgs,
          "Edit properties of an existing setup.")
_register("delete_setup", sup.delete_setup, DeleteSetupArgs,
          "Delete an analysis setup by name.")

# ---- solve ----
_register("analyze_setup", slv.analyze_setup, AnalyzeSetupArgs,
          "Run analysis on a setup (or all setups if name='all'). Blocks by default.")
_register("get_solve_status", slv.get_solve_status, GetSolveStatusArgs,
          "Check solve status of a named setup.")

# ---- results / post ----
_register("get_solution_data", res.get_solution_data, GetSolutionDataArgs,
          "Fetch solution data for expressions (e.g. Torque, FluxLinkage) and dump to CSV under ./out.")
_register("get_torque", res.get_torque, GetTorqueArgs,
          "Fetch torque vs primary sweep (Time) from active Maxwell design.")
_register("get_flux_linkage", res.get_flux_linkage, GetFluxLinkageArgs,
          "Fetch flux linkage of a winding vs Time.")
_register("get_winding_inductance", res.get_winding_inductance, GetWindingInductanceArgs,
          "Winding inductance matrix summary (magnetostatic setup).")

# ---- parametric ----
_register("create_parametric_setup", prm.create_parametric_setup, CreateParametricSetupArgs,
          "Create a parametric (Optimetrics) sweep over one or more design variables.")
_register("add_variation", prm.add_variation, AddVariationArgs,
          "Add a variable range to an existing parametric setup.")
_register("analyze_parametric", prm.analyze_parametric, AnalyzeParametricArgs,
          "Run a parametric setup that was previously configured.")
_register("get_variation_table", prm.get_variation_table, GetVariationTableArgs,
          "Return the list of design variations for a parametric setup (and optionally CSV).")

# ---- fields ----
_register("get_field_points_on_contour", fld.get_field_points_on_contour, GetFieldPointsOnContourArgs,
          "Sample a field quantity along a named polyline and dump to .npy+(.csv) - good NN input features.")
_register("export_field_on_volume", fld.export_field_on_volume, ExportFieldVolumeArgs,
          "Export a field quantity over a set of named objects as an .aedtplt volume plot.")
_register("field_calculator_eval", fld.field_calculator_eval, FieldCalculatorEvalArgs,
          "Evaluate a field calculator expression at the nominal solution.")

# ---- nn loop ----
_register("run_design_vector", nnl.run_design_vector, RunDesignVectorArgs,
          "Closed-loop NN training hook: set variables, analyze one setup, return arrays and append to CSV.")


def run(transport: str = "stdio") -> None:
    """Run the MCP server (stdio by default)."""
    assert transport in ("stdio", "sse", "streamable-http")
    server.run(transport=transport)  # type: ignore[arg-type]
