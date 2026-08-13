#!/usr/bin/env python
"""Two-point F1 torque-instrument diagnostic.

Solves the contract mirror pair (id, iq, If) = (0, ±30, 2) A on the current
FEMM section and reports weighted-stress-tensor, air-gap/Arkkio, and identity
torque side by side. Not a campaign. Not evidence for threshold freezing.

    python -m eesm.run_femm_f1_instrument
    python -m eesm.run_femm_f1_instrument --mock    # wiring only, NOT evidence
    python -m eesm.run_femm_f1_instrument --check

See eesm/docs/TORQUE_INSTRUMENT_REVIEW.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from typing import Any, Dict, Optional

_EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_EESM_ROOT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from eesm.femm import extract, geometry, runtime  # noqa: E402
from eesm.femm.config import DEFAULT_CONFIG  # noqa: E402
from eesm.femm.extract import decompose_mirror_torque  # noqa: E402
from eesm.femm.mock_femm import MockFemm  # noqa: E402

DEFAULT_OUTPUT = os.path.join(
    _REPO_ROOT, "out", "eesm",
    "femm_f1_instrument_line_%s" % date.today().strftime("%Y%m%d"),
)

MIRROR_IQ_A = 30.0
MIRROR_IF_A = 2.0
CLOSURE_GATE = (0.90, 1.10)
MIRROR_GATE_PCT = 3.0


class RunnerRefusal(RuntimeError):
    """A precondition failed. Nothing was solved."""


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def _k(torque_nm: Optional[float], identity_nm: Optional[float]) -> Optional[float]:
    if torque_nm is None or identity_nm is None:
        return None
    if identity_nm == 0.0:
        return None
    return torque_nm / identity_nm


def _closure_pass(k_positive: Optional[float], k_negative: Optional[float]) -> bool:
    lo, hi = CLOSURE_GATE
    return (
        k_positive is not None and k_negative is not None
        and lo <= k_positive <= hi and lo <= k_negative <= hi
    )


def _instrument_block(name: str, positive: Dict[str, Any],
                      negative: Dict[str, Any],
                      torque_key: str) -> Dict[str, Any]:
    t_pos = positive.get(torque_key)
    t_neg = negative.get(torque_key)
    identity_pos = positive.get("torque_identity_nm")
    identity_neg = negative.get("torque_identity_nm")
    parts = decompose_mirror_torque(float(t_pos), float(t_neg))
    k_pos = _k(t_pos, identity_pos)
    k_neg = _k(t_neg, identity_neg)
    return {
        "name": name,
        "torque_key": torque_key,
        "t_positive_nm": t_pos,
        "t_negative_nm": t_neg,
        "k_positive": k_pos,
        "k_negative": k_neg,
        "even_nm": parts["even_nm"],
        "odd_nm": parts["odd_nm"],
        "mean_abs_nm": parts["mean_abs_nm"],
        "asymmetry_pct": parts["asymmetry_pct"],
        "mirror_gate_pct": MIRROR_GATE_PCT,
        "mirror_gate_pass": parts["asymmetry_pct"] <= MIRROR_GATE_PCT,
        "closure_gate": list(CLOSURE_GATE),
        "closure_gate_pass": _closure_pass(k_pos, k_neg),
    }


def _flux_mirror(positive: Dict[str, Any],
                 negative: Dict[str, Any]) -> Dict[str, Any]:
    ld_p, ld_n = positive["lambda_d_wb"], negative["lambda_d_wb"]
    lq_p, lq_n = positive["lambda_q_wb"], negative["lambda_q_wb"]
    ld_mean = 0.5 * (abs(ld_p) + abs(ld_n))
    lq_mean = 0.5 * (abs(lq_p) + abs(lq_n))
    return {
        "lambda_d_positive_wb": ld_p,
        "lambda_d_negative_wb": ld_n,
        "lambda_q_positive_wb": lq_p,
        "lambda_q_negative_wb": lq_n,
        "lambda_d_mirror_pct": (
            100.0 * abs(ld_p - ld_n) / ld_mean if ld_mean else 0.0
        ),
        "lambda_q_mirror_pct": (
            100.0 * abs(lq_p + lq_n) / lq_mean if lq_mean else 0.0
        ),
        "theta_electrical_deg": positive.get("theta_electrical_deg"),
    }


def build_verdict(positive: Dict[str, Any],
                  negative: Dict[str, Any]) -> Dict[str, Any]:
    identity = _instrument_block(
        "identity", positive, negative, "torque_identity_nm")
    wst = _instrument_block(
        "weighted_stress_tensor", positive, negative, "torque_fem_nm")
    gap = _instrument_block(
        "airgap_arkkio", positive, negative, "torque_gap_nm")
    # Identity compared to itself is k=1 by construction; use it only as
    # the even-bias / mirror check, not as an F1 instrument.
    identity["closure_gate_pass"] = True
    identity["k_positive"] = 1.0
    identity["k_negative"] = 1.0
    return {
        "flux": _flux_mirror(positive, negative),
        "identity": identity,
        "weighted_stress_tensor": wst,
        "airgap_arkkio": gap,
        "primary_instrument": "weighted_stress_tensor",
        "f1_pass": bool(wst["mirror_gate_pass"] and wst["closure_gate_pass"]),
        "second_method_usable": bool(
            gap["mirror_gate_pass"] and gap["closure_gate_pass"]
        ),
    }


def guard_output_root(root: str) -> None:
    markers = (
        "campaign_freeze.json",
        "canonical_campaign.csv",
        "campaign_report.json",
    )
    found = [name for name in markers
             if os.path.exists(os.path.join(root, name))]
    if found:
        raise RunnerRefusal(
            "Refusing run: %s holds campaign evidence %s."
            % (root, sorted(found))
        )


def run(out_root: str, mock: bool = False) -> Dict[str, Any]:
    guard_output_root(out_root)
    os.makedirs(out_root, exist_ok=True)
    cfg = DEFAULT_CONFIG
    handle = MockFemm(cfg=cfg) if mock else runtime.resolve_femm()
    document_path = os.path.join(out_root, "eesm_sector.fem")
    report = None
    try:
        if mock:
            report = geometry.build_sector(handle, cfg)
        else:
            report = geometry.open_and_build(handle, document_path, cfg)
        positive = extract.extract_point(
            handle, 0.0, MIRROR_IQ_A, MIRROR_IF_A, cfg=cfg)
        negative = extract.extract_point(
            handle, 0.0, -MIRROR_IQ_A, MIRROR_IF_A, cfg=cfg)
    finally:
        closer = getattr(handle, "closefemm", None)
        if callable(closer):
            try:
                closer()
            except BaseException:
                pass

    if not positive.get("converged") or not negative.get("converged"):
        raise RunnerRefusal(
            "Solve failed: positive=%s negative=%s"
            % (positive.get("solver_status"), negative.get("solver_status"))
        )

    payload = {
        "evidence": False if mock else True,
        "mock": mock,
        "contract": os.path.join("eesm", "docs", "TORQUE_INSTRUMENT_REVIEW.md"),
        "points": {
            "positive": {"id_a": 0.0, "iq_a": MIRROR_IQ_A, "if_a": MIRROR_IF_A},
            "negative": {"id_a": 0.0, "iq_a": -MIRROR_IQ_A, "if_a": MIRROR_IF_A},
        },
        "build": report.as_dict() if report is not None else None,
        "rows": {"pure_q_pos": positive, "q_neg": negative},
        "verdict": build_verdict(positive, negative),
        "availability": runtime.availability_payload(),
    }
    payload["availability"]["real_solve_performed"] = not mock
    return payload


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        print(json.dumps(runtime.availability_payload(), indent=2))
        return 0

    if args.mock:
        print("NOT EVIDENCE: --mock drives MockFemm. No FEMM solve ran.")

    try:
        payload = run(args.out, mock=args.mock)
    except (RunnerRefusal, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    out_path = os.path.join(args.out, "f1_instrument.json")
    with open(out_path, "w", encoding="utf-8") as stream:
        json.dump(_json_ready(payload), stream, indent=2, sort_keys=True)
        stream.write("\n")

    verdict = payload["verdict"]
    print("wrote %s" % out_path)
    print("evidence: %s" % payload["evidence"])
    print("flux lambda_d mirror: %.4f%%" % verdict["flux"]["lambda_d_mirror_pct"])
    print("identity even: %.6f N.m  asym: %.4f%%"
          % (verdict["identity"]["even_nm"],
             verdict["identity"]["asymmetry_pct"]))
    print("WST   even: %.6f N.m  asym: %.4f%%  k=%s / %s  mirror=%s closure=%s"
          % (verdict["weighted_stress_tensor"]["even_nm"],
             verdict["weighted_stress_tensor"]["asymmetry_pct"],
             verdict["weighted_stress_tensor"]["k_positive"],
             verdict["weighted_stress_tensor"]["k_negative"],
             verdict["weighted_stress_tensor"]["mirror_gate_pass"],
             verdict["weighted_stress_tensor"]["closure_gate_pass"]))
    print("gap   even: %.6f N.m  asym: %.4f%%  k=%s / %s  mirror=%s closure=%s"
          % (verdict["airgap_arkkio"]["even_nm"],
             verdict["airgap_arkkio"]["asymmetry_pct"],
             verdict["airgap_arkkio"]["k_positive"],
             verdict["airgap_arkkio"]["k_negative"],
             verdict["airgap_arkkio"]["mirror_gate_pass"],
             verdict["airgap_arkkio"]["closure_gate_pass"]))
    print("F1 (primary=WST): %s" % verdict["f1_pass"])
    print("second method usable: %s" % verdict["second_method_usable"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
