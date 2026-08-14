"""Sárén MTPA residual identities. No FEMM."""

from __future__ import annotations

import numpy as np
import pytest

from metrics.saren_mtpa import mtpa_residual, newton_current_step


def test_linear_synrm_mtpa_is_equal_id_iq():
    residual = mtpa_residual(
        id_a=10.0,
        iq_a=10.0,
        lambda_d=0.02,
        lambda_q=0.01,
        Ldd=0.002,
        Ldq=0.0,
        Lqd=0.0,
        Lqq=0.001,
    )
    assert residual == pytest.approx(0.0, abs=1e-12)


def test_newton_step_moves_toward_equal_id_iq():
    step = newton_current_step(
        id_a=10.0,
        iq_a=1.0,
        lambda_d=0.02,
        lambda_q=0.001,
        Ldd=0.002,
        Ldq=0.0,
        Lqd=0.0,
        Lqq=0.001,
    )
    # Residual e = (Ld-Lq)(id^2 - iq^2) > 0; step should reduce |id| or raise |iq|.
    assert step[0] < 0 or step[1] > 0
    assert np.linalg.norm(step) > 0.0
