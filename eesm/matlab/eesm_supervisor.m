function y = eesm_supervisor(u)
%EESM_SUPERVISOR Zero current commands when the LUT status is infeasible.
%   u = [id_ref; iq_ref; if_ref; status_code]
id_r = u(1);
iq_r = u(2);
if_r = u(3);
status = u(4);
if status > 0 && all(isfinite([id_r, iq_r, if_r]))
    y = [id_r; iq_r; if_r];
else
    y = [0; 0; 0];
end
end
