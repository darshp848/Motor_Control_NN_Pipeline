function setup_eesm_simulink(repoRoot)
%SETUP_EESM_SIMULINK Import LUT, build the model, run one smoke scenario.

arguments
    repoRoot (1, 1) string = string(fileparts(fileparts(fileparts(mfilename("fullpath")))))
end

addpath(fullfile(repoRoot, "eesm", "matlab"));
params = init_eesm_corroboration(repoRoot);
assert(height(params.lut.table) == 64, "expected 64 LUT rows");
assert(params.not_electromagnetic_truth);
modelName = build_eesm_corroboration_model(repoRoot);
assert(isfile(fullfile(repoRoot, "eesm", "matlab", modelName + ".slx")));
results = run_eesm_scenarios(repoRoot, "rated_torque_step");
disp(jsonencode(results, PrettyPrint=true));
if ~strcmp(results.scenarios(1).status, "completed")
    error("setup_eesm_simulink:SmokeFailed", "%s", results.scenarios(1).message);
end
end
