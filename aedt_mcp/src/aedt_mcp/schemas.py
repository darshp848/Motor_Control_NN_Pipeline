"""Pydantic argument models for each MCP tool.

Kept separate so they can be unit-tested without launching AEDT, and so the
FastMCP server can attach them as JSON Schema `inputSchema`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ------------------------------------------------------------ project/design
class OpenDesignArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = Field(
        ..., description="AEDT solver/design type to open or create."
    )
    project: str | None = Field(
        None, description="Project name. None = use active / create new."
    )
    design: str | None = Field(None, description="Design name. None = create new.")


class SaveProjectArgs(BaseModel):
    project: str | None = Field(None, description="Project name to save. None = active project.")
    path: str | None = Field(None, description="Optional absolute .aedt path to save as.")


class CloseProjectArgs(BaseModel):
    project: str | None = Field(None, description="Project name. None = active project.")
    save: bool = Field(True, description="Save before closing if True.")


class ListDesignsArgs(BaseModel):
    pass


class SafeStatusArgs(BaseModel):
    pass


class DiagnoseEnvironmentArgs(BaseModel):
    pass


class ParseLogsArgs(BaseModel):
    log_dir: str = Field("tmp/aedt_jobs", description="Workspace-local log directory to scan.")
    max_matches: int = Field(200, ge=1, le=2000)


class ClassifyFailureArgs(BaseModel):
    text: str


class GenerateLaunchProcedureArgs(BaseModel):
    port: int = Field(50052, ge=1, le=65535)


class GenerateAttachTestArgs(BaseModel):
    port: int = Field(50052, ge=1, le=65535)
    include_scriptenv: bool = True


class WriteProcedureArgs(BaseModel):
    procedure: dict[str, Any]
    filename: str | None = None


class ResumeFromUserOutputArgs(BaseModel):
    output: str


class GenerateScriptEnvProbeArgs(BaseModel):
    port: int = Field(50052, ge=1, le=65535)
    timeout_seconds: int = Field(45, ge=5, le=600)


class ResumeScriptEnvProbeArgs(BaseModel):
    output: str


class GenerateProjectProbeProcedureArgs(BaseModel):
    project: str = Field(..., description="Source .aedt project path. The procedure opens only a workspace copy.")
    port: int = Field(50052, ge=1, le=65535)
    job_id: str = "project_probe"
    timeout_seconds: int = Field(120, ge=10, le=3600)


class ResumeProjectProbeArgs(BaseModel):
    output: str


class GenerateFemExportPlanArgs(BaseModel):
    stage: Literal["smoke", "validation", "full"] = "smoke"
    i_rated: float = Field(150.0, gt=0)
    theta_re: float = 0.0


class GenerateFemExportProcedureArgs(BaseModel):
    project_copy: str = Field(..., description="Workspace-local copied .aedt path from project probe result.")
    design: str
    setup: str
    port: int = Field(50052, ge=1, le=65535)
    job_id: str = "fem_export_smoke"
    phase_a: str = "Phase_A"
    phase_b: str = "Phase_B"
    phase_c: str = "Phase_C"
    n_id: int = Field(2, ge=2, le=40)
    n_iq: int = Field(2, ge=2, le=40)
    i_rated: float = Field(150.0, gt=0)
    theta_re: float = 0.0
    solve: bool = True
    resume: bool = True
    out: str = "data/flux_map_fem.csv"
    timeout_seconds: int = Field(1800, ge=30, le=86400)


class ResumeFemExportArgs(BaseModel):
    output: str


class FemExportStatusArgs(BaseModel):
    job_id: str = "fem_export_smoke"
    out: str = "data/flux_map_fem.csv"


class GeneratePyAedtLaunchOwnedProbeArgs(BaseModel):
    port: int = Field(50052, ge=1, le=65535)
    job_id: str = "pyaedt_launch_probe"
    timeout_seconds: int = Field(180, ge=30, le=3600)


class ResumePyAedtLaunchOwnedProbeArgs(BaseModel):
    output: str


class GeneratePyAedtProjectProbeProcedureArgs(BaseModel):
    project: str = Field(..., description="Source .aedt project path. The procedure opens only a workspace copy.")
    port: int = Field(50052, ge=1, le=65535)
    job_id: str = "pyaedt_project_probe"
    timeout_seconds: int = Field(300, ge=30, le=7200)


class ResumePyAedtProjectProbeArgs(BaseModel):
    output: str


class GeneratePyAedtFemExportProcedureArgs(BaseModel):
    project_copy: str = Field(..., description="Workspace-local copied .aedt path from PyAEDT project probe result.")
    design: str
    setup: str
    port: int = Field(50052, ge=1, le=65535)
    job_id: str = "pyaedt_fem_export_smoke"
    phase_a: str = "Phase_A"
    phase_b: str = "Phase_B"
    phase_c: str = "Phase_C"
    n_id: int = Field(2, ge=2, le=40)
    n_iq: int = Field(2, ge=2, le=40)
    i_rated: float = Field(150.0, gt=0)
    theta_re: float = 0.0
    solve: bool = True
    resume: bool = True
    out: str = "data/flux_map_fem.csv"
    timeout_seconds: int = Field(1800, ge=30, le=86400)


class ResumePyAedtFemExportArgs(BaseModel):
    output: str


class PyAedtExportStatusArgs(BaseModel):
    job_id: str = "pyaedt_fem_export_smoke"
    out: str = "data/flux_map_fem.csv"


class GenerateAedtProcessInventoryArgs(BaseModel):
    pass


class GenerateStopDuplicateAedtProcedureArgs(BaseModel):
    keep_pid: int | None = Field(None, ge=1)


class ResumeProcessCleanupArgs(BaseModel):
    output: str


# --------------------------------------------------------------- modeler
class CreateBoxArgs(BaseModel):
    position: list[float] = Field(..., description="Origin [x,y,z] in model units (m).")
    sizes: list[float] = Field(..., description="Sizes [dx,dy,dz]. Strings with units OK: '5mm'.")
    name: str = Field("box1", description="Object name.")
    material: str | None = Field(None, description="Optional material to assign.")


class CreateCylinderArgs(BaseModel):
    center: list[float] = Field(..., description="Center [x,y,z].")
    radius: float | str = Field(..., description="Cylinder radius.")
    height: float | str = Field(..., description="Cylinder height.")
    axis: Literal["X", "Y", "Z"] = Field("Z", description="Cylinder axis.")
    name: str = Field("cyl1", description="Object name.")
    material: str | None = Field(None, description="Optional material to assign.")


class CreateCircleArgs(BaseModel):
    center: list[float] = Field(..., description="Center [x,y,z].")
    radius: float | str = Field(...)
    plane: Literal["XY", "YZ", "ZX"] = Field("XY")
    name: str = Field("circle1")


class CreatePolylineArgs(BaseModel):
    points: list[float | str] = Field(
        ..., description="Flat list [x,y,z, x,y,z, ...] - 3N entries."
    )
    name: str = Field("poly1")
    close: bool = Field(False, description="Close into a polygon.")

    @model_validator(mode="after")
    def _check_points(self) -> CreatePolylineArgs:
        if len(self.points) % 3 != 0:
            raise ValueError(f"points must have 3N entries, got {len(self.points)}")
        return self


class CreateRectangleArgs(BaseModel):
    position: list[float]
    sizes: list[float]  # [w, h]
    plane: Literal["XY", "YZ", "ZX"] = Field("XY")
    name: str = Field("rect1")
    material: str | None = None


class BooleanArgs(BaseModel):
    operation: Literal["unite", "intersect", "subtract"]
    object_list: list[str] = Field(..., description="Primary object(s).")
    tool_list: list[str] | None = Field(None, description="Tools for subtract/intersect.")
    keep_originals: bool = Field(False)


class DuplicateAroundAxisArgs(BaseModel):
    object_name: str
    axis: Literal["X", "Y", "Z"]
    count: int = Field(..., ge=1)
    angle: float | str = Field(..., description="Total angle in degrees (e.g. 360/N).")
    change_name: bool = Field(True, description="Auto-rename created copies.")


class DuplicateAlongLineArgs(BaseModel):
    object_name: str
    vector: list[float]
    count: int = Field(..., ge=1)


class MoveTranslateArgs(BaseModel):
    object_names: list[str]
    vector: list[float] = Field(..., description="Displacement [dx,dy,dz].")


class RotateArgs(BaseModel):
    object_names: list[str]
    axis: Literal["X", "Y", "Z"]
    angle_deg: float


class ImportGeometryArgs(BaseModel):
    path: str = Field(..., description="Absolute path to STEP/IGES Parasolid file.")
    name: str | None = None


# ----------------------------------------------------------- materials
class AddMaterialArgs(BaseModel):
    name: str
    permittivity: float | None = None
    permeability: float | None = None
    conductivity: float | None = None
    extra_props: dict[str, Any] | None = Field(
        None, description="Extra pyaedt material properties (e.g. {'youngs_modulus':'200GPa'}."
    )


class AssignMaterialArgs(BaseModel):
    objects: list[str]
    material: str


class ListMaterialsArgs(BaseModel):
    pass


# ------------------------------------------------------------- variables
class SetVariableArgs(BaseModel):
    name: str = Field(..., description="Prefix '$' for project variable, none for design variable.")
    expression: str | float = Field(..., description="e.g. '1mm' or 0.5.")


class ListVariablesArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"


# ---------------------------------------------------- boundaries / excitations
class CreateCoilArgs(BaseModel):
    object_name: str = Field(..., description="Conductor (e.g. coil cross-section / wire region).")
    coil_name: str = Field("Coil", description="Coil terminal name.")
    current_value: str | float = Field("1A", description="Rated current.")
    polarity: Literal["positive", "negative"] = "positive"
    coil_type: Literal["solid", "stranded", "grouped"] = "stranded"
    number_of_conductors: int = Field(1, ge=1)


class CreateWindingArgs(BaseModel):
    objects: list[str] = Field(..., description="Coil object names to include in this winding.")
    name: str = Field("Winding")
    winding_type: Literal["current", "voltage", "external"] = "current"
    value: str | float = Field("0A")
    is_winding: bool = Field(True, description="True = source winding; False = sink/return.")


class AssignCurrentArgs(BaseModel):
    objects: list[str]
    current: str | float = Field("1A")
    name: str = "Current1"


class AssignVoltageArgs(BaseModel):
    objects: list[str]
    voltage: str | float = Field("0V")
    name: str = "Voltage1"


class AssignMagnetizationArgs(BaseModel):
    object_name: str
    magnitude: float = Field(..., description="Magnitude in Tesla.")
    direction: list[float] = Field(..., description="Magnetization direction [x,y,z].")
    name: str = "Mag1"


class AssignRotateMotionArgs(BaseModel):
    rotor_band_object: str = Field(..., description="Band / air gap region object.")
    name: str = "Motion1"
    angular_velocity_rpm: float = Field(0.0)
    motion_type: Literal["continuous", "limited", "oscillating"] = "continuous"
    initial_angle_deg: float = 0.0
    positive: bool = True


class CreateBoundaryDependentArgs(BaseModel):
    faces: list[int]
    master: bool = Field(True, description="True = master boundary; False = dependent/slave.")
    name: str = "Sym1"


# ------------------------------------------------------------- mesh
class AssignLengthMeshArgs(BaseModel):
    objects: list[str]
    max_length: str | float = Field("2mm")
    name: str = "LengthMesh"


class AssignSkinDepthMeshArgs(BaseModel):
    objects: list[str]
    skin_depth: str | float = Field("0.5mm")
    name: str = "SkinMesh"


class SurfaceMeshArgs(BaseModel):
    faces: list[int]
    num_elements: int = Field(1000, ge=1)
    name: str = "SurfaceMesh"


# --------------------------------------------------------------- setup
class CreateSetupArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    setup_type: str = Field(
        "Transient", description="maxwell3d: 'Magnetostatic'/'Transient'/'EddyCurrent'. hfss: 'HFSSDrivenDefault'."
    )
    name: str = "Setup1"
    stop_time: str | float | None = Field(None, description="Transient stop time (e.g. '10ms').")
    time_step: str | float | None = Field(None, description="Transient time step (e.g. '0.5ms').")
    save_fields: bool = True
    max_passes: int = Field(10, ge=1)
    max_passes_hfss: int = Field(20, ge=1)
    minimum_converged_passes: int = 1
    energy_error: float = Field(1.0, description="Maxwell energy error %.")
    additional_props: dict[str, Any] | None = None


class EditSetupArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    name: str
    props: dict[str, Any]


class DeleteSetupArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    name: str


# --------------------------------------------------------------- solve
class AnalyzeSetupArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    name: str = Field(..., description="Setup name to analyze. 'all' = analyze all setups.")
    block: bool = Field(True, description="Wait for completion before returning.")


class GetSolveStatusArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    name: str


# ---------------------------------------------------------- results / post
class GetSolutionDataArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    expressions: list[str] = Field(..., description="e.g. ['Torque1','FluxLinkage(PHASEA)'].")
    primary_sweep: str = Field("Time", description="Independent variable (Time, Angle, Freq, ...).")
    setup: str | None = Field(None, description="Setup name. None = first / default.")
    report_category: str | None = None
    variations: dict[str, str] | None = None
    write_csv: bool = Field(True)
    csv_basename: str | None = None


class GetTorqueArgs(BaseModel):
    setup: str | None = None
    torque_name: str = "Torque1"
    write_csv: bool = True


class GetFluxLinkageArgs(BaseModel):
    setup: str | None = None
    winding: str = "PHASEA"
    write_csv: bool = True


class GetWindingInductanceArgs(BaseModel):
    setup: str | None = None
    winding: str = "PHASEA"


# ----------------------------------------------------------- parametric
class CreateParametricSetupArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    variables: list[str] = Field(..., description="Names of design variables to sweep.")
    point_count: int = Field(5, ge=1, description="Points per variable (uniform sweep LIN).")
    sweep_type: Literal["LinearCount", "LinearStep", "SingleValue"] = "LinearCount"
    setup_name: str = "Setup1"
    name: str = "Parametric1"
    save_fields: bool = False


class AddVariationArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    parametric_name: str
    variable: str
    start: str | float
    stop: str | float
    count: int = Field(5, ge=1)
    sweep_type: Literal["LinearCount", "LinearStep", "SingleValue"] = "LinearCount"


class AnalyzeParametricArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    parametric_name: str = "Parametric1"


class GetVariationTableArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    parametric_name: str = "Parametric1"
    write_csv: bool = True


# ----------------------------------------------------------------- fields
class GetFieldPointsOnContourArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    polyline_name: str = Field(..., description="Polyline along which to sample the field.")
    field: str = Field("B", description="Field symbol (B, H, J, E, ...).")
    quantity: Literal["Mag", "X", "Y", "Z", "Real", "Imag", "Complex"] = "Mag"
    setup: str | None = None
    write_npy: bool = True


class ExportFieldVolumeArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    objects: list[str]
    field: str = "B"
    quantity: str = "Mag"
    setup: str | None = None
    write_npy: bool = True


class FieldCalculatorEvalArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    expression: str = Field(..., description="Field calculator expression.")


# ------------------------------------------------------------ nn loop
class RunDesignVectorArgs(BaseModel):
    design_type: Literal["hfss", "maxwell3d"] = "maxwell3d"
    variables: dict[str, str | float] = Field(..., description="Variable -> value mapping to apply.")
    expressions: list[str] = Field(..., description="Result expressions to sample.")
    primary_sweep: str = "Time"
    setup: str = "Setup1"
    append_csv: str | None = Field(
        None, description="If given, append the result vector to this CSV (good for NN training datasets)."
    )
