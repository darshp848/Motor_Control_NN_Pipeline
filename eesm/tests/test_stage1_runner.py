"""Tests for eesm/run_synthetic_stage1.py (temp output dir)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

_EESM = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_RUNNER = os.path.join(_EESM, "run_synthetic_stage1.py")
_MANIFEST = os.path.join(_EESM, "configs", "synthetic_eesm_manifest.json")


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_synthetic_stage1", _RUNNER
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_default_artifacts_stay_outside_the_eesm_source_tree():
    runner = _load_runner()
    output = os.path.normcase(runner.resolve_output_dir({}, None))
    source = os.path.normcase(os.path.abspath(_EESM)) + os.sep

    assert not output.startswith(source)
    assert os.path.join("out", "eesm") in output


def test_run_stage1_writes_expected_outputs(tmp_path):
    runner = _load_runner()
    out = tmp_path / "stage1_out"
    summary = runner.run_stage1(
        manifest_path=_MANIFEST,
        output_dir=str(out),
        oracle_n_id=5,
        oracle_n_iq=5,
        oracle_n_if=3,
        feasible_rpm=1500.0,
        feasible_t_ref=20.0,
        infeasible_rpm=1500.0,
        infeasible_t_ref=1.0e6,
    )

    expected = [
        "oracle_dense_map.csv",
        "samples_tensor_grid.csv",
        "samples_random.csv",
        "samples_latin_hypercube.csv",
        "stage1_synthetic_summary.json",
    ]
    for name in expected:
        assert (out / name).is_file(), f"missing {name}"
    assert not (out / "samples_sequential_placeholder.csv").exists()

    assert summary["status"] == "ok"
    assert summary["oracle"]["n_rows"] == 5 * 5 * 3
    assert summary["smoke_validation"]["ok"] is True
    fe = summary["scheduler"]["feasible_example"]
    assert fe["status"] in ("feasible", "saturated_to_boundary")
    assert fe["id_ref_a"] is not None
    assert fe["torque_ok"] is True
    assert fe["domain_ok"] is True

    ie = summary["scheduler"]["infeasible_example"]
    assert ie["status"] in ("infeasible", "out_of_domain", "search_failed")
    assert ie["id_ref_a"] is None
    assert ie["torque_ok"] is False
    assert ie["voltage_ok"] is False
    assert ie["stator_current_ok"] is False
    assert ie["field_current_ok"] is False
    assert ie["domain_ok"] is False

    with open(out / "stage1_synthetic_summary.json", encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["experiment_id"] == summary["experiment_id"]
    assert "feasible_example" in on_disk["scheduler"]
