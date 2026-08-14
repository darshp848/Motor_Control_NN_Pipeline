function lut = import_eesm_lut(csvPath, metadataPath)
%IMPORT_EESM_LUT Validate and load a foundry EESM Simulink LUT.
%   LUT = IMPORT_EESM_LUT(CSVPATH, METADATAPATH) refuses to create
%   lookup tables unless columns, hashes, monotonic axes, and status
%   codes match the export contract.

arguments
    csvPath (1, 1) string
    metadataPath (1, 1) string
end

required = [ ...
    "rpm_mech", "t_ref_nm", "id_ref_a", "iq_ref_a", "if_ref_a", ...
    "status", "torque_ok", "voltage_ok", "stator_current_ok", ...
    "field_current_ok", "domain_ok", "uncertainty_ok"];
validStatus = ["feasible", "saturated_to_boundary", "infeasible"];

meta = jsondecode(fileread(metadataPath));
if ~isfield(meta, "lut_sha256") || strlength(string(meta.lut_sha256)) == 0
    error("import_eesm_lut:MissingHash", "metadata missing lut_sha256");
end
if ~isfield(meta, "audit_model_sha256") || ~isfield(meta, "model_sha256")
    error("import_eesm_lut:MissingModelHash", "metadata missing model hashes");
end
if string(meta.audit_model_sha256) ~= string(meta.model_sha256)
    error("import_eesm_lut:HashMismatch", "audit-model hash mismatch");
end

fid = fopen(csvPath, "r");
if fid < 0
    error("import_eesm_lut:OpenFailed", "cannot open %s", csvPath);
end
cleaner = onCleanup(@() fclose(fid));
bytes = fread(fid, inf, "*uint8");
clear cleaner
digest = lower(sprintf("%02x", sha256_bytes(bytes)));
if digest ~= lower(string(meta.lut_sha256))
    error("import_eesm_lut:LutHashMismatch", "LUT file hash does not match metadata");
end

tbl = readtable(csvPath, "TextType", "string");
missing = setdiff(required, string(tbl.Properties.VariableNames));
if ~isempty(missing)
    error("import_eesm_lut:MissingColumns", "missing columns: %s", strjoin(missing, ", "));
end
if height(tbl) < 1
    error("import_eesm_lut:Empty", "LUT has no rows");
end
if any(~ismember(tbl.status, validStatus))
    error("import_eesm_lut:BadStatus", "LUT contains an unknown status code");
end

rpmGrid = unique(tbl.rpm_mech);
tGrid = unique(tbl.t_ref_nm);
if ~issorted(rpmGrid) || ~issorted(tGrid)
    error("import_eesm_lut:Axes", "rpm or torque axes are not sorted");
end
if any(diff(rpmGrid) <= 0) || any(diff(tGrid) <= 0)
    error("import_eesm_lut:Axes", "rpm or torque axes are not strictly monotonic");
end

nRpm = numel(rpmGrid);
nT = numel(tGrid);
if height(tbl) ~= nRpm * nT
    error("import_eesm_lut:Grid", "LUT is not a complete rpm x torque grid");
end

idTbl = nan(nRpm, nT);
iqTbl = nan(nRpm, nT);
ifTbl = nan(nRpm, nT);
statusTbl = zeros(nRpm, nT);
statusCode = dictionary(validStatus, [1, 2, 0]);

for i = 1:height(tbl)
    ir = find(rpmGrid == tbl.rpm_mech(i), 1);
    it = find(tGrid == tbl.t_ref_nm(i), 1);
    if isempty(ir) || isempty(it)
        error("import_eesm_lut:Grid", "row is not on the declared grid");
    end
    idTbl(ir, it) = tbl.id_ref_a(i);
    iqTbl(ir, it) = tbl.iq_ref_a(i);
    ifTbl(ir, it) = tbl.if_ref_a(i);
    statusTbl(ir, it) = statusCode(tbl.status(i));
end

lut = struct();
lut.rpm_grid = rpmGrid;
lut.t_grid = tGrid;
lut.Id_ref = idTbl;
lut.Iq_ref = iqTbl;
lut.If_ref = ifTbl;
lut.Status = statusTbl;
lut.table = tbl;
lut.metadata = meta;
lut.not_electromagnetic_truth = true;
end

function digest = sha256_bytes(bytes)
md = java.security.MessageDigest.getInstance("SHA-256");
md.update(bytes);
digest = typecast(md.digest, "uint8");
end
