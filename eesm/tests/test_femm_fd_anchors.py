"""FD Hessian anchor selection and arithmetic. No live FEMM."""

from __future__ import annotations

import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eesm.femm import fd_anchors  # noqa: E402
from eesm.femm.fd_anchors import FdAnchorRefusal  # noqa: E402


def _row(point_id, role, region, id_a, iq_a, if_a, ld=0.0, lq=0.0, lf=0.0):
    return {
        "point_id": point_id,
        "role": role,
        "region": region,
        "converged": "True",
        "id_a": id_a,
        "iq_a": iq_a,
        "if_a": if_a,
        "lambda_d_wb": ld,
        "lambda_q_wb": lq,
        "lambda_field_wb": lf,
    }


def test_selection_is_train_interior_with_offset_room():
    rows = [
        _row("aaaaaaaaaaaaaaaa", "scheduler_audit", "interior", -40, 40, 6),
        _row("bbbbbbbbbbbbbbbb", "train", "saturation", -40, 40, 14),
        _row("cccccccccccccccc", "train", "interior", -0.5, 40, 6),
        _row("dddddddddddddddd", "train", "interior", -40, 40, 6),
        _row("eeeeeeeeeeeeeeee", "train", "interior", -80, 20, 2),
        _row("ffffffffffffffff", "train", "interior", -20, 80, 10),
        _row("1111111111111111", "train", "interior", -60, 60, 4),
        _row("2222222222222222", "train", "interior", -30, 30, 8),
        _row("3333333333333333", "train", "interior", -90, 50, 3),
        _row("4444444444444444", "train", "interior", -50, 90, 7),
        _row("5555555555555555", "train", "interior", -70, 10, 5),
        _row("6666666666666666", "selection", "interior", -40, 50, 6),
    ]
    picked = fd_anchors.select_anchors(rows, n=4)
    assert len(picked) == 4
    assert {item["point_id"] for item in picked}.isdisjoint(
        {"aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", "cccccccccccccccc",
         "6666666666666666"}
    )
    again = fd_anchors.select_anchors(rows, n=4)
    assert [item["point_id"] for item in again] == [item["point_id"] for item in picked]


def test_jacobian_recovers_linear_mock_inductance():
    plus = {"lambda_d_wb": 0.1, "lambda_q_wb": 0.04, "lambda_field_wb": 0.2}
    minus = {"lambda_d_wb": -0.1, "lambda_q_wb": 0.04, "lambda_field_wb": 0.0}
    jac = fd_anchors.jacobian_from_offsets(plus, minus, 1.0)
    assert jac["d_lambda_d"] == pytest.approx(0.1)
    assert jac["d_lambda_q"] == pytest.approx(0.0)
    assert jac["d_lambda_f"] == pytest.approx(0.1)


def test_three_halves_reciprocity_is_the_reported_metric():
    jac_id = {"d_lambda_d": 0.004, "d_lambda_q": 0.0, "d_lambda_f": 0.0075}
    jac_iq = {"d_lambda_d": 0.0, "d_lambda_q": 0.002, "d_lambda_f": 0.0}
    jac_if = {"d_lambda_d": 0.005, "d_lambda_q": 0.0, "d_lambda_f": 0.12}
    assembled = fd_anchors.assemble_inductance(jac_id, jac_iq, jac_if)
    assert assembled["reciprocity_fd_minus_1p5_Ldf"] == pytest.approx(0.0)
    assert assembled["reciprocity_fd_naive"] == pytest.approx(0.0025)
    # Sector λf is 1/4 of terminal; 4 Lfd = 1.5 Ldf for this fixture
    # only after that scale. The fixture above is already 3/2 in raw Lfd.


def test_refuses_preserved_roots(tmp_path):
    with pytest.raises(FdAnchorRefusal, match="preserved"):
        fd_anchors.run_fd_anchors(source=str(tmp_path), out_dir=fd_anchors.TASK9_ROOT)


def test_mock_fd_run_writes_new_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    # Build a tiny fake campaign the selector can read.
    import csv
    centres = [
        ("a000000000000001", -40.0, 40.0, 3.0),
        ("a000000000000002", -80.0, 20.0, 2.0),
        ("a000000000000003", -20.0, 80.0, 10.0),
        ("a000000000000004", -60.0, 60.0, 5.0),
        ("a000000000000005", -30.0, 30.0, 8.0),
        ("a000000000000006", -90.0, 50.0, 4.0),
        ("a000000000000007", -50.0, 90.0, 7.0),
        ("a000000000000008", -70.0, 15.0, 6.0),
    ]
    with open(source / "femm_results.csv", "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "point_id", "role", "region", "converged",
            "id_a", "iq_a", "if_a",
            "lambda_d_wb", "lambda_q_wb", "lambda_field_wb",
        ])
        writer.writeheader()
        for point_id, id_a, iq_a, if_a in centres:
            writer.writerow({
                "point_id": point_id, "role": "train", "region": "interior",
                "converged": "True",
                "id_a": id_a, "iq_a": iq_a, "if_a": if_a,
                "lambda_d_wb": 0.0, "lambda_q_wb": 0.0, "lambda_field_wb": 0.0,
            })
    out = tmp_path / "fd"
    payload = fd_anchors.run_fd_anchors(
        source=str(source), out_dir=str(out), n_anchors=8, use_mock=True,
    )
    assert payload["n_offset_solves"] == 48
    assert payload["backend"] == "mock_femm"
    assert (out / "fd_anchor_centres.json").is_file()
    assert (out / "fd_anchors.json").is_file()
    first = payload["anchors"][0]["inductance"]
    # Linear mock: Ldd, Lqq recover the stand-in machine; field reciprocity
    # is naive (Lfd = Ldf), which the 3/2 residual must report as nonzero.
    from eesm.femm.mock_femm import LinearSalientMachine
    machine = LinearSalientMachine()
    assert first["Ldd"] == pytest.approx(machine.ld_h, rel=1e-9)
    assert first["Lqq"] == pytest.approx(machine.lq_h, rel=1e-9)
    assert first["Ldf"] == pytest.approx(machine.mutual_field_d_wb_per_a, rel=1e-9)
    assert first["reciprocity_fd_minus_1p5_Ldf"] != pytest.approx(0.0)
    with pytest.raises(FdAnchorRefusal, match="already has"):
        fd_anchors.run_fd_anchors(
            source=str(source), out_dir=str(out), n_anchors=8, use_mock=True,
        )
