#!/usr/bin/env python
"""Close the F1 instrument question: detent vs type-7 gap vs virtual work.

Solves (0,0,If), (0,+iq,If), (0,-iq,If) on the spec section with a type-7
band labeled <No Mesh>. Reports:

  - WST even part vs field-only torque (detent hypothesis)
  - mo_gapintegral raw and x4 (FEMM half-model benchmark returns FULL T)
  - virtual-work dW'/dθ from sliding-band inner angle ±δ

    python -m eesm.run_femm_f1_blocker
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date
from typing import Any, Dict, Optional

_EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_EESM_ROOT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from dataclasses import replace

from eesm.femm import extract, geometry, runtime  # noqa: E402
from eesm.femm.config import DEFAULT_CONFIG  # noqa: E402
from eesm.femm.extract import decompose_mirror_torque  # noqa: E402

IQ_A = 30.0
IF_A = 2.0
VW_DELTA_DEG = 0.1
MIRROR_GATE_PCT = 3.0
CLOSURE = (0.90, 1.10)

DEFAULT_OUTPUT = os.path.join(
    _REPO_ROOT, "out", "eesm",
    "femm_f1_blocker_%s" % date.today().strftime("%Y%m%d"),
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


def _k(torque: Optional[float], identity: Optional[float]) -> Optional[float]:
    if torque is None or identity in (None, 0.0):
        return None
    return torque / identity


def _close_solution(handle: Any) -> None:
    closer = getattr(handle, "mo_close", None)
    if callable(closer):
        try:
            closer()
        except BaseException:
            pass


def _virtual_work_moverotate(handle: Any, iq_a: float,
                             if_a: float) -> Optional[Dict[str, Any]]:
    """T ≈ (W'(+δ) − W'(−δ)) / 2δ by rotating rotor groups and remeshing."""
    delta = VW_DELTA_DEG
    groups = DEFAULT_CONFIG.api.torque_groups
    try:
        extract.set_currents(handle, 0.0, iq_a, if_a, 150.0, DEFAULT_CONFIG)
        energies = {}
        for name, angle in (("plus", delta), ("minus", -delta)):
            handle.mi_clearselected()
            for group in groups:
                handle.mi_selectgroup(group)
            handle.mi_moverotate(0.0, 0.0, angle if name == "plus" else -2.0 * delta)
            handle.mi_analyze(1)
            handle.mi_loadsolution()
            energies[name] = extract.read_sector_coenergy(handle, DEFAULT_CONFIG)
            _close_solution(handle)
        dtheta = 2.0 * math.radians(delta)
        t_sector = (energies["plus"] - energies["minus"]) / dtheta
        t_full = t_sector * DEFAULT_CONFIG.extraction.torque_sector_multiplier
        return {
            "delta_deg": delta,
            "coenergy_plus_j": energies["plus"],
            "coenergy_minus_j": energies["minus"],
            "t_sector_nm": t_sector,
            "t_full_x4_nm": t_full,
        }
    except BaseException as exc:
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _solve(handle: Any, id_a: float, iq_a: float, if_a: float,
           rotor_angle_deg: float = 0.0) -> Dict[str, Any]:
    result = extract.extract_point(
        handle, id_a, iq_a, if_a, rotor_angle_deg=rotor_angle_deg,
        cfg=DEFAULT_CONFIG)
    if not result.get("converged"):
        raise RuntimeError("solve failed: %s" % result.get("solver_status"))
    try:
        result["coenergy_j"] = extract.read_sector_coenergy(
            handle, DEFAULT_CONFIG)
    except BaseException as exc:
        result["coenergy_j"] = None
        result["coenergy_error"] = "%s: %s" % (type(exc).__name__, exc)
    _close_solution(handle)
    return result


def _instrument(name: str, t_pos: float, t_neg: float,
                id_pos: float, id_neg: float) -> Dict[str, Any]:
    parts = decompose_mirror_torque(t_pos, t_neg)
    k_pos = _k(t_pos, id_pos)
    k_neg = _k(t_neg, id_neg)
    lo, hi = CLOSURE
    return {
        "name": name,
        "t_positive_nm": t_pos,
        "t_negative_nm": t_neg,
        **parts,
        "k_positive": k_pos,
        "k_negative": k_neg,
        "mirror_gate_pass": parts["asymmetry_pct"] <= MIRROR_GATE_PCT,
        "closure_gate_pass": (
            k_pos is not None and k_neg is not None
            and lo <= k_pos <= hi and lo <= k_neg <= hi
        ),
    }


def run(out_root: str) -> Dict[str, Any]:
    os.makedirs(out_root, exist_ok=True)
    # Band off: type-7 refused twice. This run is detent vs WST even-part
    # on the known-solving section, plus virtual work via remesh at ±δ
    # using mi_moverotate on the rotor groups.
    cfg = DEFAULT_CONFIG
    handle = runtime.resolve_femm()
    document = os.path.join(out_root, "eesm_sector.fem")
    report = geometry.open_and_build(handle, document, cfg)
    try:
        field = _solve(handle, 0.0, 0.0, IF_A)
        positive = _solve(handle, 0.0, IQ_A, IF_A)
        negative = _solve(handle, 0.0, -IQ_A, IF_A)
        vw = _virtual_work_moverotate(handle, IQ_A, IF_A)
    finally:
        closer = getattr(handle, "closefemm", None)
        if callable(closer):
            try:
                closer()
            except BaseException:
                pass

    wst = _instrument(
        "wst_x4",
        positive["torque_fem_nm"], negative["torque_fem_nm"],
        positive["torque_identity_nm"], negative["torque_identity_nm"])
    gap_raw = None
    gap_x4 = None
    if positive.get("torque_gap_nm") is not None:
        gap_raw = _instrument(
            "gap_raw",
            positive["torque_gap_sector_nm"], negative["torque_gap_sector_nm"],
            positive["torque_identity_nm"], negative["torque_identity_nm"])
        gap_x4 = _instrument(
            "gap_x4",
            positive["torque_gap_nm"], negative["torque_gap_nm"],
            positive["torque_identity_nm"], negative["torque_identity_nm"])

    detent_wst = field["torque_fem_nm"]
    return {
        "evidence": True,
        "build": report.as_dict(),
        "rows": {
            "field_only": field,
            "pure_q_pos": positive,
            "q_neg": negative,
        },
        "verdict": {
            "flux_lambda_d_mirror_pct": (
                100.0 * abs(positive["lambda_d_wb"] - negative["lambda_d_wb"])
                / (0.5 * (abs(positive["lambda_d_wb"])
                          + abs(negative["lambda_d_wb"])))
            ),
            "field_only_wst_nm": detent_wst,
            "wst_even_nm": wst["even_nm"],
            "detent_explains_even": abs(detent_wst - wst["even_nm"]) <= (
                0.25 * max(abs(wst["even_nm"]), 1e-6)
            ),
            "wst": wst,
            "gap_raw": gap_raw,
            "gap_x4": gap_x4,
            "virtual_work": vw,
            "mesh_elements": positive.get("mesh_elements"),
        },
    }


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        payload = run(args.out)
    except (RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    path = os.path.join(args.out, "f1_blocker.json")
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(_ready(payload), stream, indent=2, sort_keys=True)
        stream.write("\n")
    v = payload["verdict"]
    print("wrote %s" % path)
    print("mesh: %s" % v["mesh_elements"])
    print("lambda_d mirror: %.4f%%" % v["flux_lambda_d_mirror_pct"])
    print("field-only WST: %.6f N.m" % v["field_only_wst_nm"])
    print("WST even:       %.6f N.m  asym=%.4f%%  detent_explains=%s"
          % (v["wst_even_nm"], v["wst"]["asymmetry_pct"],
             v["detent_explains_even"]))
    print("WST k: %s / %s  mirror=%s closure=%s"
          % (v["wst"]["k_positive"], v["wst"]["k_negative"],
             v["wst"]["mirror_gate_pass"], v["wst"]["closure_gate_pass"]))
    if v["gap_raw"] is None:
        print("gap: not read (sliding band off)")
    else:
        print("gap raw k: %s / %s  asym=%.4f%%"
              % (v["gap_raw"]["k_positive"], v["gap_raw"]["k_negative"],
                 v["gap_raw"]["asymmetry_pct"]))
        print("gap x4  k: %s / %s  asym=%.4f%%"
              % (v["gap_x4"]["k_positive"], v["gap_x4"]["k_negative"],
                 v["gap_x4"]["asymmetry_pct"]))
    print("virtual work: %s" % v["virtual_work"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
