"""Shared IPM pipeline utilities (Stage 0 freeze).

Physics, domain labels, manifests, and data QA used by train / validate /
MTPA / audit scripts and regression tests.
"""

from .domain import (
    DomainLabel,
    TrainingDomain,
    domain_from_training_xy,
    label_point,
    label_points,
)
from .physics import (
    abc_from_dq,
    dq_from_abc,
    electromagnetic_torque,
    rpm_mech_to_we,
    stator_voltage_dq,
    v_max_svpwm,
)

__all__ = [
    "DomainLabel",
    "TrainingDomain",
    "domain_from_training_xy",
    "label_point",
    "label_points",
    "abc_from_dq",
    "dq_from_abc",
    "electromagnetic_torque",
    "rpm_mech_to_we",
    "stator_voltage_dq",
    "v_max_svpwm",
]
