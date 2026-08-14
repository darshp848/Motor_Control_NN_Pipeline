function params = init_eesm_corroboration(repoRoot)
%INIT_EESM_CORROBORATION Load machine constants and the exported LUT.

arguments
    repoRoot (1, 1) string = string(fileparts(fileparts(fileparts(mfilename("fullpath")))))
end

manifestPath = fullfile(repoRoot, "eesm", "configs", "eesm_experiment_manifest.json");
scenarioPath = fullfile(repoRoot, "eesm", "configs", "simulink_scenarios.json");
lutCsv = fullfile(repoRoot, "out", "eesm", "simulink_export_20260813", "eesm_lut.csv");
lutMeta = fullfile(repoRoot, "out", "eesm", "simulink_export_20260813", "eesm_lut_metadata.json");

manifest = jsondecode(fileread(manifestPath));
scenarios = jsondecode(fileread(scenarioPath));
lut = import_eesm_lut(lutCsv, lutMeta);

params = struct();
params.pole_pairs = manifest.machine.pole_pairs;
params.rs_ohm = manifest.machine.rs_ohm;
params.rf_ohm = manifest.machine.rf_ohm;
params.vdc_v = manifest.machine.vdc_v;
params.v_max_phase_peak = manifest.machine.vdc_v / sqrt(3);
params.i_s_max_peak_a = manifest.machine.i_s_max_peak_a;
params.i_f_max_a = manifest.machine.i_f_max_a;
params.t_rated_nm = manifest.machine.t_rated_nm;
params.J_kgm2 = scenarios.mechanical_inertia_kgm2;
params.tau_s_s = scenarios.stator_current_tau_s;
params.tau_f_s = scenarios.field_current_tau_s;
params.Ts = scenarios.sample_time_s;
params.lut = lut;
params.scenarios = scenarios;
params.not_electromagnetic_truth = true;

assignin("base", "eesm_params", params);
assignin("base", "rpm_grid", lut.rpm_grid);
assignin("base", "t_grid", lut.t_grid);
assignin("base", "Id_ref", lut.Id_ref);
assignin("base", "Iq_ref", lut.Iq_ref);
assignin("base", "If_ref", lut.If_ref);
assignin("base", "Status_tbl", lut.Status);
assignin("base", "pole_pairs", params.pole_pairs);
assignin("base", "J_kgm2", params.J_kgm2);
assignin("base", "tau_s_s", params.tau_s_s);
assignin("base", "tau_f_s", params.tau_f_s);
assignin("base", "Ts_eesm", params.Ts);
end
