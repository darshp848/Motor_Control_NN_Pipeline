function modelName = build_eesm_corroboration_model(repoRoot)
%BUILD_EESM_CORROBORATION_MODEL Create the map-based corroboration plant.
%   Built-in Simulink blocks only. The plant is a first-order current
%   tracker plus identity torque; it is not FEM truth.

arguments
    repoRoot (1, 1) string = string(fileparts(fileparts(fileparts(mfilename("fullpath")))))
end

if isempty(ver("Simulink"))
    error("build_eesm_corroboration_model:NoSimulink", "Simulink is not installed");
end

init_eesm_corroboration(repoRoot);
modelName = "eesm_corroboration";
modelDir = fullfile(repoRoot, "eesm", "matlab");
modelPath = fullfile(modelDir, modelName + ".slx");
if bdIsLoaded(modelName)
    close_system(modelName, 0);
end
if isfile(modelPath)
    delete(modelPath);
end

new_system(modelName);
open_system(modelName);
set_param(modelName, ...
    "SolverType", "Fixed-step", ...
    "Solver", "ode3", ...
    "FixedStep", "Ts_eesm", ...
    "StopTime", "1.5", ...
    "SaveOutput", "on", ...
    "SignalLogging", "on", ...
    "SignalLoggingName", "logsout");

add_block("simulink/Sources/From Workspace", modelName + "/rpm_cmd", ...
    "VariableName", "rpm_cmd_ts");
add_block("simulink/Sources/From Workspace", modelName + "/t_ref_cmd", ...
    "VariableName", "t_ref_ts");
add_block("simulink/Sources/Constant", modelName + "/pole_pairs_c", ...
    "Value", "pole_pairs");

lutParams = { ...
    "BreakpointsForDimension1", "rpm_grid", ...
    "BreakpointsForDimension2", "t_grid", ...
    "InterpMethod", "Linear point-slope", ...
    "ExtrapMethod", "Clip"};
add_block("simulink/Lookup Tables/n-D Lookup Table", modelName + "/Id_lut", ...
    lutParams{:}, "Table", "Id_ref", "NumberOfTableDimensions", "2");
add_block("simulink/Lookup Tables/n-D Lookup Table", modelName + "/Iq_lut", ...
    lutParams{:}, "Table", "Iq_ref", "NumberOfTableDimensions", "2");
add_block("simulink/Lookup Tables/n-D Lookup Table", modelName + "/If_lut", ...
    lutParams{:}, "Table", "If_ref", "NumberOfTableDimensions", "2");
add_block("simulink/Lookup Tables/n-D Lookup Table", modelName + "/Status_lut", ...
    "BreakpointsForDimension1", "rpm_grid", ...
    "BreakpointsForDimension2", "t_grid", ...
    "Table", "Status_tbl", ...
    "NumberOfTableDimensions", "2", ...
    "InterpMethod", "Nearest", ...
    "ExtrapMethod", "Clip");

add_block("simulink/Signal Routing/Mux", modelName + "/sup_mux", "Inputs", "4");
add_block("simulink/User-Defined Functions/Interpreted MATLAB Function", ...
    modelName + "/Supervisor", "MATLABFcn", "eesm_supervisor");
add_block("simulink/Signal Routing/Demux", modelName + "/sup_demux", "Outputs", "3");

add_block("simulink/Continuous/Transfer Fcn", modelName + "/Id_dyn", ...
    "Numerator", "[1]", "Denominator", "[tau_s_s 1]");
add_block("simulink/Continuous/Transfer Fcn", modelName + "/Iq_dyn", ...
    "Numerator", "[1]", "Denominator", "[tau_s_s 1]");
add_block("simulink/Continuous/Transfer Fcn", modelName + "/If_dyn", ...
    "Numerator", "[1]", "Denominator", "[tau_f_s 1]");

add_block("simulink/Signal Routing/Mux", modelName + "/tq_mux", "Inputs", "4");
add_block("simulink/User-Defined Functions/Interpreted MATLAB Function", ...
    modelName + "/IdentityTorque", "MATLABFcn", "eesm_identity_torque");

add_block("simulink/Math Operations/Gain", modelName + "/InvJ", "Gain", "1/J_kgm2");
add_block("simulink/Continuous/Integrator", modelName + "/SpeedInt", ...
    "InitialCondition", "0");
add_block("simulink/Math Operations/Gain", modelName + "/Rad2Rpm", ...
    "Gain", "60/(2*pi)");

add_block("simulink/Sinks/To Workspace", modelName + "/log_id", ...
    "VariableName", "id_a", "SaveFormat", "Timeseries");
add_block("simulink/Sinks/To Workspace", modelName + "/log_iq", ...
    "VariableName", "iq_a", "SaveFormat", "Timeseries");
add_block("simulink/Sinks/To Workspace", modelName + "/log_if", ...
    "VariableName", "if_a", "SaveFormat", "Timeseries");
add_block("simulink/Sinks/To Workspace", modelName + "/log_T", ...
    "VariableName", "torque_nm", "SaveFormat", "Timeseries");
add_block("simulink/Sinks/To Workspace", modelName + "/log_rpm", ...
    "VariableName", "rpm_mech", "SaveFormat", "Timeseries");
add_block("simulink/Sinks/To Workspace", modelName + "/log_status", ...
    "VariableName", "status_code", "SaveFormat", "Timeseries");

add_line(modelName, "rpm_cmd/1", "Id_lut/1");
add_line(modelName, "rpm_cmd/1", "Iq_lut/1");
add_line(modelName, "rpm_cmd/1", "If_lut/1");
add_line(modelName, "rpm_cmd/1", "Status_lut/1");
add_line(modelName, "t_ref_cmd/1", "Id_lut/2");
add_line(modelName, "t_ref_cmd/1", "Iq_lut/2");
add_line(modelName, "t_ref_cmd/1", "If_lut/2");
add_line(modelName, "t_ref_cmd/1", "Status_lut/2");

add_line(modelName, "Id_lut/1", "sup_mux/1");
add_line(modelName, "Iq_lut/1", "sup_mux/2");
add_line(modelName, "If_lut/1", "sup_mux/3");
add_line(modelName, "Status_lut/1", "sup_mux/4");
add_line(modelName, "sup_mux/1", "Supervisor/1");
add_line(modelName, "Supervisor/1", "sup_demux/1");
add_line(modelName, "sup_demux/1", "Id_dyn/1");
add_line(modelName, "sup_demux/2", "Iq_dyn/1");
add_line(modelName, "sup_demux/3", "If_dyn/1");

add_line(modelName, "Id_dyn/1", "tq_mux/1");
add_line(modelName, "Iq_dyn/1", "tq_mux/2");
add_line(modelName, "If_dyn/1", "tq_mux/3");
add_line(modelName, "pole_pairs_c/1", "tq_mux/4");
add_line(modelName, "tq_mux/1", "IdentityTorque/1");
add_line(modelName, "IdentityTorque/1", "InvJ/1");
add_line(modelName, "InvJ/1", "SpeedInt/1");
add_line(modelName, "SpeedInt/1", "Rad2Rpm/1");

add_line(modelName, "Id_dyn/1", "log_id/1");
add_line(modelName, "Iq_dyn/1", "log_iq/1");
add_line(modelName, "If_dyn/1", "log_if/1");
add_line(modelName, "IdentityTorque/1", "log_T/1");
add_line(modelName, "Rad2Rpm/1", "log_rpm/1");
add_line(modelName, "Status_lut/1", "log_status/1");

Simulink.BlockDiagram.arrangeSystem(modelName);
save_system(modelName, modelPath);
end
