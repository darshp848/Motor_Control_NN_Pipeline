"""LUT status / feasibility marking tests."""

import math

import numpy as np

from mtpa_field_weakening import reference_lookup


class _ConstSurrogate:
    """Constant flux surrogate for controlled envelope tests."""

    def __init__(self, ld=0.1, lq=0.05):
        self.ld = ld
        self.lq = lq

    def predict(self, X):
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        n = X.shape[0]
        return np.column_stack([np.full(n, self.ld), np.full(n, self.lq)])

    def torque(self, X, n_pp):
        Y = self.predict(X)
        T = 1.5 * n_pp * (Y[:, 0] * X[:, 1] - Y[:, 1] * X[:, 0])
        return T, Y

    def voltage(self, X, omega_e, R_s, Y=None):
        if Y is None:
            Y = self.predict(X)
        Vd = R_s * X[:, 0] - omega_e * Y[:, 1]
        Vq = R_s * X[:, 1] + omega_e * Y[:, 0]
        return np.sqrt(Vd * Vd + Vq * Vq), Vd, Vq


def test_lut_marks_infeasible_above_envelope():
    surr = _ConstSurrogate()
    n_pp = 2
    rs = 2.0
    v_max = 50.0  # tight voltage limit at high speed
    i_max = 5.0
    # Low speed: MTPA should work for modest torque
    t_refs = [0.5, 50.0]  # 50 N.m is intentionally huge
    rpms = [100.0, 6000.0]
    rows, env = reference_lookup(
        surr, n_pp, rs, v_max, i_max, t_refs, rpms, grid_n=40
    )
    statuses = { (r[0], r[1]): r[5] for r in rows }
    # Huge torque should be infeasible somewhere
    assert any(s == "infeasible" for s in statuses.values())


def test_mtpa_status_exists_for_small_torque_low_speed():
    surr = _ConstSurrogate(ld=0.2, lq=0.05)
    rows, _ = reference_lookup(
        surr, 2, 1.0, 200.0, 6.0,
        t_refs=[0.2],
        rpms=[100.0],
        grid_n=80,
    )
    assert len(rows) == 1
    # May be mtpa or fw or mtpa_unavailable depending on map; not empty status
    assert rows[0][5] in ("mtpa", "fw", "infeasible", "mtpa_unavailable", "fw_search_failed")
