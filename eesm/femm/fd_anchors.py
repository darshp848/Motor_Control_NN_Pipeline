"""Finite-difference L_diff anchors. Diagnostic validation truth only.

Does not freeze thresholds, fit a surrogate, or write into an existing
campaign root. Centres come from a finished FEMM campaign; only the six
offset points are solved.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import extract, geometry, runtime
from .config import DEFAULT_CONFIG

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SOURCE = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_equal_budget_20260813"
)
DEFAULT_OUT = os.path.join(REPO_ROOT, "out", "eesm", "femm_fd_anchors_20260813")
TASK9_ROOT = os.path.join(REPO_ROOT, "out", "eesm", "task9_baseline")

H_ID_A = 1.0
H_IQ_A = 1.0
H_IF_A = 0.2
N_ANCHORS = 8
ID_BOUNDS = (-120.0, 0.0)
IQ_BOUNDS = (0.0, 120.0)
IF_BOUNDS = (0.0, 15.0)

OFFSETS: Sequence[Tuple[str, float, float, float]] = (
    ("id_plus", H_ID_A, 0.0, 0.0),
    ("id_minus", -H_ID_A, 0.0, 0.0),
    ("iq_plus", 0.0, H_IQ_A, 0.0),
    ("iq_minus", 0.0, -H_IQ_A, 0.0),
    ("if_plus", 0.0, 0.0, H_IF_A),
    ("if_minus", 0.0, 0.0, -H_IF_A),
)


class FdAnchorRefusal(RuntimeError):
    """A selection or write invariant failed."""


def _flux(row: Mapping[str, Any]) -> Tuple[float, float, float]:
    return (
        float(row["lambda_d_wb"]),
        float(row["lambda_q_wb"]),
        float(row["lambda_field_wb"]),
    )


def has_offset_room(id_a: float, iq_a: float, if_a: float) -> bool:
    return (
        ID_BOUNDS[0] + H_ID_A <= id_a <= ID_BOUNDS[1] - H_ID_A
        and IQ_BOUNDS[0] + H_IQ_A <= iq_a <= IQ_BOUNDS[1] - H_IQ_A
        and IF_BOUNDS[0] + H_IF_A <= if_a <= IF_BOUNDS[1] - H_IF_A
    )


def _feature(id_a: float, iq_a: float, if_a: float) -> Tuple[float, float, float]:
    return (
        (id_a - ID_BOUNDS[0]) / (ID_BOUNDS[1] - ID_BOUNDS[0]),
        (iq_a - IQ_BOUNDS[0]) / (IQ_BOUNDS[1] - IQ_BOUNDS[0]),
        (if_a - IF_BOUNDS[0]) / (IF_BOUNDS[1] - IF_BOUNDS[0]),
    )


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def eligible_centres(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    chosen: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("role") != "train" or row.get("region") != "interior":
            continue
        if str(row.get("converged")) not in ("True", "true", "1"):
            continue
        id_a = float(row["id_a"])
        iq_a = float(row["iq_a"])
        if_a = float(row["if_a"])
        if not has_offset_room(id_a, iq_a, if_a):
            continue
        chosen.append({
            "point_id": row["point_id"],
            "role": row["role"],
            "region": row["region"],
            "id_a": id_a,
            "iq_a": iq_a,
            "if_a": if_a,
            "lambda_d_wb": float(row["lambda_d_wb"]),
            "lambda_q_wb": float(row["lambda_q_wb"]),
            "lambda_field_wb": float(row["lambda_field_wb"]),
        })
    chosen.sort(key=lambda item: item["point_id"])
    return chosen


def select_anchors(
    rows: Iterable[Mapping[str, Any]], n: int = N_ANCHORS
) -> List[Dict[str, Any]]:
    """Greedy farthest-point sample of train/interior centres. Deterministic."""
    pool = eligible_centres(rows)
    if len(pool) < n:
        raise FdAnchorRefusal(
            "Refusing FD anchors: only %d eligible interiors, need %d" % (len(pool), n)
        )
    selected = [min(pool, key=lambda item: (item["if_a"], item["point_id"]))]
    while len(selected) < n:
        selected_ids = {item["point_id"] for item in selected}
        best: Optional[Dict[str, Any]] = None
        best_d = -1.0
        for cand in pool:
            if cand["point_id"] in selected_ids:
                continue
            distance = min(
                _dist(_feature(cand["id_a"], cand["iq_a"], cand["if_a"]),
                      _feature(item["id_a"], item["iq_a"], item["if_a"]))
                for item in selected
            )
            if best is None or distance > best_d or (
                distance == best_d and cand["point_id"] < best["point_id"]
            ):
                best = cand
                best_d = distance
        if best is None:
            raise FdAnchorRefusal("Refusing FD anchors: selection exhausted")
        selected.append(best)
    return selected


def jacobian_from_offsets(
    plus: Mapping[str, Any], minus: Mapping[str, Any], step: float
) -> Dict[str, float]:
    """Central difference of (λd, λq, λf)."""
    ld_p, lq_p, lf_p = _flux(plus)
    ld_m, lq_m, lf_m = _flux(minus)
    two_h = 2.0 * float(step)
    return {
        "d_lambda_d": (ld_p - ld_m) / two_h,
        "d_lambda_q": (lq_p - lq_m) / two_h,
        "d_lambda_f": (lf_p - lf_m) / two_h,
    }


def assemble_inductance(jac_id: Mapping[str, float],
                        jac_iq: Mapping[str, float],
                        jac_if: Mapping[str, float]) -> Dict[str, float]:
    ldd = jac_id["d_lambda_d"]
    ldq = jac_iq["d_lambda_d"]
    ldf = jac_if["d_lambda_d"]
    lqd = jac_id["d_lambda_q"]
    lqq = jac_iq["d_lambda_q"]
    lqf = jac_if["d_lambda_q"]
    lfd = jac_id["d_lambda_f"]
    lfq = jac_iq["d_lambda_f"]
    lff = jac_if["d_lambda_f"]
    # 90 deg model: field circuit is one pole. Four series poles make
    # terminal λf = 4 × sector circuit flux. Stator λd/λq are already
    # terminal. Live 2026-08-13 anchors: 4 Lfd − 1.5 Ldf is ~0.
    field_scale = 4.0
    lfd_t = field_scale * lfd
    lfq_t = field_scale * lfq
    lff_t = field_scale * lff
    return {
        "Ldd": ldd, "Ldq": ldq, "Ldf": ldf,
        "Lqd": lqd, "Lqq": lqq, "Lqf": lqf,
        "Lfd": lfd, "Lfq": lfq, "Lff": lff,
        "field_flux_sector_to_terminal": field_scale,
        "Lfd_terminal": lfd_t,
        "Lfq_terminal": lfq_t,
        "Lff_terminal": lff_t,
        "reciprocity_dq": ldq - lqd,
        "reciprocity_fd_minus_1p5_Ldf": lfd - 1.5 * ldf,
        "reciprocity_fq_minus_1p5_Lqf": lfq - 1.5 * lqf,
        "reciprocity_fd_naive": lfd - ldf,
        "reciprocity_fd_terminal_minus_1p5_Ldf": lfd_t - 1.5 * ldf,
        "reciprocity_fq_terminal_minus_1p5_Lqf": lfq_t - 1.5 * lqf,
    }


def _guard_root(root: str, source: str) -> None:
    real = os.path.realpath(root)
    forbidden = [
        os.path.realpath(TASK9_ROOT),
        os.path.realpath(source),
        os.path.realpath(os.path.join(REPO_ROOT, "out", "eesm",
                                      "femm_equal_budget_points_20260813")),
        os.path.realpath(os.path.join(REPO_ROOT, "out", "eesm",
                                      "femm_baseline_64_20260812")),
    ]
    for path in forbidden:
        if real == path or real.startswith(path + os.sep):
            raise FdAnchorRefusal(
                "Refusing FD anchors: destination is a preserved root (%s)" % path
            )


def _read_campaign_rows(source: str) -> List[Dict[str, str]]:
    path = os.path.join(source, "femm_results.csv")
    if not os.path.isfile(path):
        raise FdAnchorRefusal("Refusing FD anchors: missing %s" % path)
    with open(path, newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _write_json(path: str, payload: Mapping[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _solve_offset(handle: Any, centre: Mapping[str, Any],
                  name: str, d_id: float, d_iq: float, d_if: float) -> Dict[str, Any]:
    result = extract.extract_point(
        handle,
        float(centre["id_a"]) + d_id,
        float(centre["iq_a"]) + d_iq,
        float(centre["if_a"]) + d_if,
        rotor_angle_deg=0.0,
        cfg=DEFAULT_CONFIG,
    )
    closer = getattr(handle, "mo_close", None)
    if callable(closer):
        try:
            closer()
        except BaseException:
            pass
    if not result.get("converged"):
        raise FdAnchorRefusal(
            "Refusing to continue: offset %s of %s failed (%s)"
            % (name, centre["point_id"], result.get("solver_status"))
        )
    result["offset"] = name
    result["centre_point_id"] = centre["point_id"]
    return result


def run_fd_anchors(
    source: str = DEFAULT_SOURCE,
    out_dir: str = DEFAULT_OUT,
    n_anchors: int = N_ANCHORS,
    use_mock: bool = False,
) -> Dict[str, Any]:
    _guard_root(out_dir, source)
    if os.path.exists(os.path.join(out_dir, "fd_anchors.json")):
        raise FdAnchorRefusal(
            "Refusing FD anchors: %s already has fd_anchors.json" % out_dir
        )
    rows = _read_campaign_rows(source)
    anchors = select_anchors(rows, n=n_anchors)
    os.makedirs(out_dir, exist_ok=True)
    freeze = {
        "not_a_threshold_freeze": True,
        "not_a_fit": True,
        "not_a_promotion_gate": True,
        "source_campaign": os.path.abspath(source),
        "h_id_a": H_ID_A,
        "h_iq_a": H_IQ_A,
        "h_if_a": H_IF_A,
        "n_anchors": n_anchors,
        "centres": [
            {key: item[key] for key in (
                "point_id", "role", "region", "id_a", "iq_a", "if_a",
                "lambda_d_wb", "lambda_q_wb", "lambda_field_wb",
            )}
            for item in anchors
        ],
    }
    freeze_path = os.path.join(out_dir, "fd_anchor_centres.json")
    _write_json(freeze_path, freeze)

    if use_mock:
        from .mock_femm import MockFemm
        handle: Any = MockFemm(cfg=DEFAULT_CONFIG)
        backend = "mock_femm"
    else:
        handle = runtime.resolve_femm()
        backend = "femm_4.2"
        geometry.open_and_build(
            handle, os.path.join(out_dir, "eesm_sector.fem"), DEFAULT_CONFIG
        )

    reports: List[Dict[str, Any]] = []
    try:
        for centre in anchors:
            offsets: Dict[str, Dict[str, Any]] = {}
            for name, d_id, d_iq, d_if in OFFSETS:
                offsets[name] = _solve_offset(handle, centre, name, d_id, d_iq, d_if)
            jac_id = jacobian_from_offsets(
                offsets["id_plus"], offsets["id_minus"], H_ID_A
            )
            jac_iq = jacobian_from_offsets(
                offsets["iq_plus"], offsets["iq_minus"], H_IQ_A
            )
            jac_if = jacobian_from_offsets(
                offsets["if_plus"], offsets["if_minus"], H_IF_A
            )
            reports.append({
                "centre": {
                    key: centre[key] for key in (
                        "point_id", "id_a", "iq_a", "if_a",
                        "lambda_d_wb", "lambda_q_wb", "lambda_field_wb",
                    )
                },
                "inductance": assemble_inductance(jac_id, jac_iq, jac_if),
                "offsets": {
                    name: {
                        "id_a": offsets[name]["id_a"],
                        "iq_a": offsets[name]["iq_a"],
                        "if_a": offsets[name]["if_a"],
                        "lambda_d_wb": offsets[name]["lambda_d_wb"],
                        "lambda_q_wb": offsets[name]["lambda_q_wb"],
                        "lambda_field_wb": offsets[name]["lambda_field_wb"],
                        "mesh_elements": offsets[name].get("mesh_elements"),
                    }
                    for name, _d_id, _d_iq, _d_if in OFFSETS
                },
            })
    finally:
        closer = getattr(handle, "closefemm", None)
        if callable(closer):
            try:
                closer()
            except BaseException:
                pass

    payload = {
        "backend": backend,
        "n_anchors": len(reports),
        "n_offset_solves": len(reports) * len(OFFSETS),
        "h_id_a": H_ID_A,
        "h_iq_a": H_IQ_A,
        "h_if_a": H_IF_A,
        "not_a_threshold_freeze": True,
        "not_a_fit": True,
        "not_a_promotion_gate": True,
        "convention": "eesm/docs/DQ_CONVENTIONS.md",
        "anchors": reports,
    }
    _write_json(os.path.join(out_dir, "fd_anchors.json"), payload)
    return payload


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--n", type=int, default=N_ANCHORS)
    parser.add_argument("--mock", action="store_true")
    ns = parser.parse_args(argv)
    try:
        payload = run_fd_anchors(ns.source, ns.out, ns.n, use_mock=ns.mock)
    except FdAnchorRefusal as exc:
        print("REFUSED: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps({
        "out": os.path.abspath(ns.out),
        "backend": payload["backend"],
        "n_anchors": payload["n_anchors"],
        "n_offset_solves": payload["n_offset_solves"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
