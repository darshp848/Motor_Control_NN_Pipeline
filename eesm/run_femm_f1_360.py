#!/usr/bin/env python
"""F1 mirror pair on the 360 deg model (no antiperiodic cuts).

Compares T_even to the 90 deg sector result. If T_even collapses, the
residual was a sector-boundary artifact.

    python -m eesm.run_femm_f1_360
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import date
from typing import Any, Dict

_EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_EESM_ROOT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from eesm.femm import extract, geometry, runtime
from eesm.femm.config import DEFAULT_CONFIG
from eesm.femm.extract import decompose_mirror_torque

IQ_A = 30.0
IF_A = 2.0
OUT = os.path.join(
    _REPO_ROOT, "out", "eesm",
    "femm_f1_360_%s" % date.today().strftime("%Y%m%d"),
)


def _ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_ready(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def _close_sol(handle: Any) -> None:
    closer = getattr(handle, "mo_close", None)
    if callable(closer):
        try:
            closer()
        except BaseException:
            pass


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    cfg = replace(
        DEFAULT_CONFIG,
        geometry=replace(DEFAULT_CONFIG.geometry, full_machine=True),
    )
    handle = runtime.resolve_femm()
    document = os.path.join(OUT, "eesm_360.fem")
    report = geometry.open_and_build(handle, document, cfg)
    try:
        field = extract.extract_point(handle, 0.0, 0.0, IF_A, cfg=cfg)
        _close_sol(handle)
        if not field.get("converged"):
            print("field-only failed: %s" % field.get("solver_status"),
                  file=sys.stderr)
            return 2
        pos = extract.extract_point(handle, 0.0, IQ_A, IF_A, cfg=cfg)
        _close_sol(handle)
        if not pos.get("converged"):
            print("pure_q failed: %s" % pos.get("solver_status"),
                  file=sys.stderr)
            return 2
        neg = extract.extract_point(handle, 0.0, -IQ_A, IF_A, cfg=cfg)
        _close_sol(handle)
        if not neg.get("converged"):
            print("q_neg failed: %s" % neg.get("solver_status"),
                  file=sys.stderr)
            return 2
    finally:
        closer = getattr(handle, "closefemm", None)
        if callable(closer):
            try:
                closer()
            except BaseException:
                pass

    wst = decompose_mirror_torque(pos["torque_fem_nm"], neg["torque_fem_nm"])
    identity = decompose_mirror_torque(
        pos["torque_identity_nm"], neg["torque_identity_nm"])
    k_pos = pos["torque_fem_nm"] / pos["torque_identity_nm"]
    k_neg = neg["torque_fem_nm"] / neg["torque_identity_nm"]
    k_odd = wst["odd_nm"] / identity["odd_nm"] if identity["odd_nm"] else None
    ld_mean = 0.5 * (abs(pos["lambda_d_wb"]) + abs(neg["lambda_d_wb"]))
    payload = {
        "evidence": True,
        "full_machine": True,
        "build": report.as_dict(),
        "rows": {"field_only": field, "pure_q_pos": pos, "q_neg": neg},
        "verdict": {
            "mesh_elements": pos.get("mesh_elements"),
            "theta_electrical_deg": pos.get("theta_electrical_deg"),
            "field_lambda_d_wb": field["lambda_d_wb"],
            "field_lambda_q_wb": field["lambda_q_wb"],
            "field_wst_nm": field["torque_fem_nm"],
            "lambda_d_mirror_pct": (
                100.0 * abs(pos["lambda_d_wb"] - neg["lambda_d_wb"]) / ld_mean
                if ld_mean else 0.0
            ),
            "wst": wst,
            "identity": identity,
            "k_positive": k_pos,
            "k_negative": k_neg,
            "k_odd": k_odd,
            "mirror_gate_pass": wst["asymmetry_pct"] <= 3.0,
            "closure_gate_pass": 0.90 <= k_pos <= 1.10 and 0.90 <= k_neg <= 1.10,
            "sector_t_even_nm": -0.043102862892537175,
        },
    }
    path = os.path.join(OUT, "f1_360.json")
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(_ready(payload), stream, indent=2, sort_keys=True)
        stream.write("\n")
    v = payload["verdict"]
    print("wrote", path)
    print("mesh:", v["mesh_elements"])
    print("field lambda_d,q: %.6f, %.6e" % (
        v["field_lambda_d_wb"], v["field_lambda_q_wb"]))
    print("field WST: %.6f N.m" % v["field_wst_nm"])
    print("lambda_d mirror: %.4f%%" % v["lambda_d_mirror_pct"])
    print("WST even: %.6f N.m  (sector was %.6f)"
          % (v["wst"]["even_nm"], v["sector_t_even_nm"]))
    print("WST asym: %.4f%%  mirror=%s" % (
        v["wst"]["asymmetry_pct"], v["mirror_gate_pass"]))
    print("k: %.4f / %.4f  k_odd=%.4f  closure=%s" % (
        v["k_positive"], v["k_negative"], v["k_odd"], v["closure_gate_pass"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
