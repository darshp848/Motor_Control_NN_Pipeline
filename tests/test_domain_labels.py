"""Domain label regression tests."""

import numpy as np

from pipeline.domain import (
    DomainLabel,
    TrainingDomain,
    default_ipm_training_domain,
    label_point,
    label_points,
    count_labels,
)


def test_domain_labels_id_positive_is_extrapolation():
    d = default_ipm_training_domain()
    assert label_point(50.0, 100.0, d) == DomainLabel.EXTRAPOLATION
    assert label_point(276.9, 3.8, d) == DomainLabel.EXTRAPOLATION


def test_domain_labels_in_box_interpolation():
    d = default_ipm_training_domain()
    # Mid-domain interior (far from edges by more than one step ~7.7A)
    lab = label_point(-150.0, 150.0, d)
    assert lab == DomainLabel.IN_DOMAIN_INTERPOLATION


def test_domain_labels_outside_iq():
    d = default_ipm_training_domain()
    assert label_point(-10.0, -5.0, d) == DomainLabel.EXTRAPOLATION
    assert label_point(-10.0, 350.0, d) == DomainLabel.EXTRAPOLATION


def test_historical_off_grid_split_pattern():
    """If half the points have Id>0, counts should reflect that."""
    d = default_ipm_training_domain()
    X = np.array([
        [-76.9, 100.0],
        [92.3, 19.0],
        [-30.0, 50.0],
        [200.0, 40.0],
    ], dtype=float)
    labs = label_points(X, d)
    c = count_labels(labs)
    assert c["extrapolation"] == 2
    assert c["in_domain_interpolation"] + c["boundary"] == 2


def test_training_domain_contains_edges():
    d = TrainingDomain(-300, 0, 0, 300, id_step=7.7, iq_step=7.7)
    assert d.contains(-300.0, 0.0)
    assert d.contains(0.0, 300.0)
    assert not d.contains(0.1, 10.0)
