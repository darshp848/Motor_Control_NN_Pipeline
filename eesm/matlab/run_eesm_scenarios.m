function results = run_eesm_scenarios(repoRoot, scenarioIds)
%RUN_EESM_SCENARIOS Simulate frozen corroboration scenarios.
%   Results are Simulink corroboration, not FEM audit.

arguments
    repoRoot (1, 1) string = string(fileparts(fileparts(fileparts(mfilename("fullpath")))))
    scenarioIds (1, :) string = []
end

params = init_eesm_corroboration(repoRoot);
modelName = "eesm_corroboration";
modelPath = fullfile(repoRoot, "eesm", "matlab", modelName + ".slx");
if ~isfile(modelPath)
    build_eesm_corroboration_model(repoRoot);
end
if ~bdIsLoaded(modelName)
    load_system(modelPath);
end

scenarios = params.scenarios.scenarios;
if isempty(scenarioIds)
    selected = scenarios;
else
    names = string({scenarios.id});
    selected = scenarios(ismember(names, scenarioIds));
end

outDir = fullfile(repoRoot, "out", "eesm", "simulink_scenarios_20260813");
if ~isfolder(outDir)
    mkdir(outDir);
end

records = struct("id", {}, "status", {}, "max_abs_id_a", {}, ...
    "max_abs_if_a", {}, "final_status_code", {}, "message", {});
for i = 1:numel(selected)
    sc = selected(i);
    assignin("base", "rpm_cmd_ts", piecewise_ts(sc.rpm_mech, params.scenarios.stop_time_s));
    assignin("base", "t_ref_ts", piecewise_ts(sc.t_ref_nm, params.scenarios.stop_time_s));
    in = Simulink.SimulationInput(modelName);
    in = in.setModelParameter("StopTime", num2str(params.scenarios.stop_time_s));
    try
        out = sim(in);
        records(i).id = string(sc.id);
        records(i).status = "completed";
        records(i).max_abs_id_a = max(abs(out.id_a.Data), [], "omitnan");
        records(i).max_abs_if_a = max(abs(out.if_a.Data), [], "omitnan");
        records(i).final_status_code = out.status_code.Data(end);
        records(i).message = "corroboration_only";
    catch err
        records(i).id = string(sc.id);
        records(i).status = "failed";
        records(i).max_abs_id_a = NaN;
        records(i).max_abs_if_a = NaN;
        records(i).final_status_code = NaN;
        records(i).message = err.message;
    end
end

results = struct();
results.created_utc = string(datetime("now", "TimeZone", "UTC", "Format", "yyyy-MM-dd'T'HH:mm:ss'Z'"));
results.role = "simulink_corroboration";
results.not_electromagnetic_truth = true;
results.matlab_version = string(version);
results.simulink_version = string(ver("Simulink").Version);
results.scenarios = records;
jsonText = jsonencode(results, PrettyPrint=true);
fid = fopen(fullfile(outDir, "simulink_scenario_results.json"), "w");
fwrite(fid, jsonText);
fclose(fid);
end

function ts = piecewise_ts(pairs, stopTime)
pts = pairs;
if iscell(pts)
    pts = cell2mat(pts);
end
t = pts(:, 1);
y = pts(:, 2);
if t(end) < stopTime
    t(end+1, 1) = stopTime;
    y(end+1, 1) = y(end);
end
ts = timeseries(y, t);
end
