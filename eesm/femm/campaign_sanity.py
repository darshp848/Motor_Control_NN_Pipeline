"""Offline sanity summary for a finished FEMM campaign root.

Reads existing CSVs. Does not launch FEMM, freeze thresholds, or fit.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

from .campaign import (
    CAMPAIGN_TORQUE_FIELD,
    campaign_torque_nm,
    load_schema,
    sha256_file,
    validate_row,
)


def _extrema(values: Iterable[float]) -> Dict[str, float]:
    xs = [float(value) for value in values]
    return {"min": min(xs), "max": max(xs), "n": len(xs)}


def summarize_campaign(root: str) -> Dict[str, Any]:
    """Build a sanity payload from `femm_results.csv` in `root`."""
    results_path = os.path.join(root, "femm_results.csv")
    points_path = os.path.join(root, "frozen_points.csv")
    status_path = os.path.join(root, "femm_status.json")
    if not os.path.isfile(results_path):
        raise FileNotFoundError("missing femm_results.csv in %s" % root)

    with open(results_path, newline="", encoding="utf-8") as stream:
        rows: List[Dict[str, str]] = list(csv.DictReader(stream))
    schema = load_schema()
    schema_fails = 0
    ident_mismatch = 0
    missing_ident = 0
    nonfinite = 0
    for row in rows:
        try:
            validate_row(row, schema)
        except Exception:
            schema_fails += 1
        try:
            torque = campaign_torque_nm(row)
        except Exception:
            missing_ident += 1
            torque = None
        identity = row.get(CAMPAIGN_TORQUE_FIELD)
        if torque is not None and identity not in ("", None):
            if abs(torque - float(identity)) > 1e-15:
                ident_mismatch += 1
        for key in ("lambda_d_wb", "lambda_q_wb", CAMPAIGN_TORQUE_FIELD):
            try:
                if not math.isfinite(float(row[key])):
                    nonfinite += 1
            except (TypeError, ValueError, KeyError):
                nonfinite += 1

    status: Optional[Dict[str, Any]] = None
    if os.path.isfile(status_path):
        with open(status_path, encoding="utf-8") as stream:
            status = json.load(stream)

    points_n = 0
    if os.path.isfile(points_path):
        with open(points_path, newline="", encoding="utf-8") as stream:
            points_n = sum(1 for _ in csv.DictReader(stream))

    payload: Dict[str, Any] = {
        "campaign_root": os.path.abspath(root),
        "verdict": (
            "schema_valid_live_rows"
            if schema_fails == 0 and missing_ident == 0 and nonfinite == 0
            else "sanity_failed"
        ),
        "not_a_threshold_freeze": True,
        "not_a_fit": True,
        "backend": None if status is None else status.get("solver_backend"),
        "status": None if status is None else status.get("status"),
        "rows": len(rows),
        "points_file_rows": points_n,
        "unique_point_ids": len({row.get("point_id") for row in rows}),
        "roles": dict(Counter(row.get("role") or "" for row in rows)),
        "regions": dict(Counter(row.get("region") or "" for row in rows)),
        "all_converged": all(str(row.get("converged")) == "True" for row in rows),
        "mesh_elements": sorted({
            int(row["mesh_elements"])
            for row in rows if row.get("mesh_elements") not in ("", None)
        }),
        "campaign_torque_field": CAMPAIGN_TORQUE_FIELD,
        "identity_equals_campaign_torque": ident_mismatch == 0 and missing_ident == 0,
        "schema_failures": schema_fails,
        "missing_identity": missing_ident,
        "nonfinite": nonfinite,
        "forbidden_lambda_f_wb": any("lambda_f_wb" in row for row in rows),
        "points_sha256": (
            sha256_file(points_path) if os.path.isfile(points_path) else None
        ),
        "results_sha256": sha256_file(results_path),
        "lambda_d_wb": _extrema(row["lambda_d_wb"] for row in rows),
        "lambda_q_wb": _extrema(row["lambda_q_wb"] for row in rows),
        "torque_identity_nm": _extrema(row["torque_identity_nm"] for row in rows),
        "wst_residual_suspect_rows": sum(
            str(row.get("torque_residual_suspect")) == "1" for row in rows
        ),
        "zero_sequence_ratio": _extrema(row["zero_sequence_ratio"] for row in rows),
    }
    return payload


def write_sanity(root: str, dest: Optional[str] = None) -> Dict[str, Any]:
    payload = summarize_campaign(root)
    path = dest or os.path.join(root, "campaign_sanity.json")
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    payload["sanity_path"] = os.path.abspath(path)
    return payload


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="Campaign directory")
    parser.add_argument("--write", action="store_true",
                        help="Write campaign_sanity.json into the root")
    ns = parser.parse_args(argv)
    payload = write_sanity(ns.root) if ns.write else summarize_campaign(ns.root)
    json.dump({
        "verdict": payload["verdict"],
        "rows": payload["rows"],
        "all_converged": payload["all_converged"],
        "schema_failures": payload["schema_failures"],
        "status": payload.get("status"),
    }, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if payload["verdict"] == "schema_valid_live_rows" else 1


if __name__ == "__main__":
    raise SystemExit(main())
