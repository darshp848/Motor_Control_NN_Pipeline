"""FEMM campaign truth lookup. No live FEMM."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from data.experiment_points import canonical_point_id
from data.femm_truth import FemmCampaignTruth


def test_origin_is_analytic_zero(tmp_path: Path):
    path = tmp_path / "femm_results.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "point_id", "role", "region", "id_a", "iq_a", "if_a",
                "lambda_d_wb", "lambda_q_wb",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "point_id": "aaaaaaaaaaaaaaaa",
            "role": "train", "region": "interior",
            "id_a": "-10", "iq_a": "20", "if_a": "3",
            "lambda_d_wb": "0.1", "lambda_q_wb": "0.2",
        })
    truth = FemmCampaignTruth(path)
    ld, lq = truth.flux(0.0, 0.0, 0.0)
    assert float(ld) == 0.0 and float(lq) == 0.0


def test_lookup_and_missing(tmp_path: Path):
    path = tmp_path / "femm_results.csv"
    id_a, iq_a, if_a = -10.0, 20.0, 3.0
    point_id = canonical_point_id(id_a, iq_a, if_a)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "point_id", "role", "region", "id_a", "iq_a", "if_a",
                "lambda_d_wb", "lambda_q_wb",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "point_id": point_id,
            "role": "train", "region": "interior",
            "id_a": id_a, "iq_a": iq_a, "if_a": if_a,
            "lambda_d_wb": "0.11", "lambda_q_wb": "-0.02",
        })
    truth = FemmCampaignTruth(path)
    ld, lq = truth.flux(id_a, iq_a, if_a)
    assert ld == pytest.approx(0.11)
    assert lq == pytest.approx(-0.02)
    with pytest.raises(KeyError, match="no FEMM truth"):
        truth.flux(-11.0, 20.0, 3.0)
