function T = eesm_identity_torque(u)
%EESM_IDENTITY_TORQUE Corroboration-only linear flux + identity torque.
%   u = [id; iq; if; pole_pairs]
id = u(1);
iq = u(2);
ifld = u(3);
p = u(4);
Ld = 0.0012;
Lq = 0.0020;
Mdf = 0.018;
ld = Ld * id + Mdf * ifld;
lq = Lq * iq;
T = 1.5 * p * (ld * iq - lq * id);
end
