#!/usr/bin/env python
"""Evaluate frozen gates, promote, then prospectively audit. No FEMM launch."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(EESM_ROOT, "src")
REPO_ROOT = os.path.dirname(EESM_ROOT)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from surrogates.registry import load_surrogate  # noqa: E402
from validation.controller_metrics import evaluate_controller_metrics  # noqa: E402
from validation.gates import evaluate_gates  # noqa: E402
from validation.promotion import promote_candidate  # noqa: E402
from validation.threshold_method import voltage_feasible  # noqa: E402


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _load_campaign(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return {row["point_id"]: row for row in rows}


def _machine(manifest: dict[str, Any]) -> dict[str, Any]:
    machine = manifest["machine"]
    return {
        "pole_pairs": int(machine["pole_pairs"]),
        "rs_ohm": float(machine["rs_ohm"]),
        "rf_ohm": float(machine["rf_ohm"]),
        "vdc_v": float(machine["vdc_v"]),
        "i_s_max_peak_a": float(machine["i_s_max_peak_a"]),
        "i_f_min_a": float(machine["i_f_min_a"]),
        "i_f_max_a": float(machine["i_f_max_a"]),
    }


def _metrics_for_ids(
    point_ids: list[str],
    predicted: np.ndarray,
    campaign: dict[str, dict[str, Any]],
    machine: dict[str, Any],
    speeds: list[float],
    allow_roles: set[str],
) -> dict[str, Any]:
    rows = []
    truth = []
    for point_id, pred in zip(point_ids, predicted):
        row = campaign[point_id]
        if row["role"] not in allow_roles:
            raise RuntimeError(
                "refusing to score role %s at %s" % (row["role"], point_id)
            )
        rows.append(row)
        truth.append([float(row["lambda_d_wb"]), float(row["lambda_q_wb"])])
    truth_y = np.asarray(truth, dtype=np.float64)
    id_a = np.array([float(row["id_a"]) for row in rows])
    iq_a = np.array([float(row["iq_a"]) for row in rows])
    if_a = np.array([float(row["if_a"]) for row in rows])
    points = {
        "id_a": id_a,
        "iq_a": iq_a,
        "if_a": if_a,
        "region": np.array([row["region"] for row in rows], dtype=object),
        "data_qa_passed": np.ones(len(rows), dtype=bool),
        "truth_feasible": voltage_feasible(id_a, iq_a, if_a, truth_y, machine),
        "predicted_feasible": voltage_feasible(id_a, iq_a, if_a, predicted, machine),
    }
    return evaluate_controller_metrics(
        points, truth_y, predicted, machine, speeds_rpm=speeds
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--study",
        default=os.path.join(REPO_ROOT, "out", "eesm", "equal_budget_femm_20260813"),
    )
    parser.add_argument(
        "--campaign",
        default=os.path.join(
            REPO_ROOT, "out", "eesm", "femm_equal_budget_20260813", "femm_results.csv"
        ),
    )
    parser.add_argument(
        "--manifest",
        default=os.path.join(EESM_ROOT, "configs", "eesm_experiment_manifest.json"),
    )
    parser.add_argument(
        "--out",
        default=os.path.join(REPO_ROOT, "out", "eesm", "phase0_close_20260813"),
    )
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_bytes())
    if manifest["gates"]["status"] != "frozen":
        print("REFUSED: thresholds are not frozen", file=sys.stderr)
        return 2
    summary = json.loads(Path(args.study, "equal_budget_summary.json").read_text(
        encoding="utf-8"
    ))
    campaign = _load_campaign(Path(args.campaign))
    machine = _machine(manifest)
    speeds = [3000.0, 9000.0]
    selection_ids = summary["role_point_ids"]["selection"]
    audit_ids = summary["role_point_ids"]["scheduler_audit"]
    if set(selection_ids) & set(audit_ids):
        raise RuntimeError("selection overlaps scheduler_audit")

    gate_results: dict[str, Any] = {}
    ranking_runs: list[dict[str, Any]] = []
    for run in summary["runs"]:
        pred_path = Path(args.study) / run["artifacts"]["predictions"]
        with pred_path.open(newline="", encoding="utf-8") as stream:
            pred_rows = list(csv.DictReader(stream))
        point_ids = [row["point_id"] for row in pred_rows]
        if point_ids != selection_ids:
            raise RuntimeError("prediction file does not match sealed selection order")
        predicted = np.array(
            [
                [float(row["lambda_d_predicted_wb"]), float(row["lambda_q_predicted_wb"])]
                for row in pred_rows
            ],
            dtype=np.float64,
        )
        metrics = _metrics_for_ids(
            point_ids, predicted, campaign, machine, speeds, {"selection"}
        )
        candidate_id = "%s|%s|%s" % (run["strategy"], run["budget"], run["family"])
        gates = evaluate_gates(metrics, manifest["gates"])
        gate_results[candidate_id] = gates
        ranking_runs.append({
            "candidate_id": candidate_id,
            "strategy": run["strategy"],
            "budget": run["budget"],
            "family": run["family"],
            "scheduler_loss_regret_w": 0.0,
            "torque_rmse_nm": float(metrics["gate_values"]["torque"]),
            "flux_rmse_wb": float(metrics["overall"]["flux"]["lambda_d_wb"]["rmse"]
                                  + metrics["overall"]["flux"]["lambda_q_wb"]["rmse"]) / 2.0,
            "training_runtime_s": float(
                json.loads(
                    (Path(args.study) / run["artifacts"]["run_metadata"]).read_text(
                        encoding="utf-8"
                    )
                ).get("training_runtime_s", 0.0)
            ),
            "gate_values": metrics["gate_values"],
            "all_required_pass": gates["all_required_pass"],
        })

    promotion = promote_candidate(ranking_runs, gate_results, "all_required_then_loss")

    audit = None
    if promotion["status"] == "promoted":
        winner = next(
            run for run in summary["runs"]
            if "%s|%s|%s" % (run["strategy"], run["budget"], run["family"])
            == promotion["candidate_id"]
        )
        model_meta = json.loads(
            (Path(args.study) / winner["artifacts"]["model_metadata"]).read_text(
                encoding="utf-8"
            )
        )
        model = load_surrogate(model_meta)
        audit_rows = [campaign[point_id] for point_id in audit_ids]
        audit_X = np.array(
            [[float(row["id_a"]), float(row["iq_a"]), float(row["if_a"])]
             for row in audit_rows],
            dtype=np.float64,
        )
        audit_pred = model.predict(audit_X)
        audit_metrics = _metrics_for_ids(
            audit_ids, audit_pred, campaign, machine, speeds, {"scheduler_audit"}
        )
        audit_gates = evaluate_gates(audit_metrics, manifest["gates"])
        audit = {
            "role": "scheduler_audit",
            "n": len(audit_ids),
            "gate_values": audit_metrics["gate_values"],
            "gates": audit_gates,
            "used_before_promotion": False,
        }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    close_payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study": os.path.abspath(args.study),
        "campaign": os.path.abspath(args.campaign),
        "manifest_sha256": _sha256_file(args.manifest),
        "ranking_runs": ranking_runs,
        "gate_results": {
            key: {"all_required_pass": value["all_required_pass"],
                  "status": value["status"],
                  "gates": value["gates"]}
            for key, value in gate_results.items()
        },
        "promotion": promotion,
        "audit": audit,
        "scheduler_loss_regret_note": (
            "Ranking uses 0 W copper-loss regret; commands were not "
            "re-optimized. Torque RMSE is the first discriminating key."
        ),
    }
    close_path = out / "phase0_close.json"
    close_path.write_text(json.dumps(close_payload, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")

    artifacts = [
        {"path": os.path.relpath(close_path, REPO_ROOT).replace("\\", "/"),
         "sha256": _sha256_file(str(close_path))},
        {"path": os.path.relpath(args.campaign, REPO_ROOT).replace("\\", "/"),
         "sha256": _sha256_file(args.campaign)},
        {"path": os.path.relpath(
            os.path.join(args.study, "equal_budget_summary.json"), REPO_ROOT
         ).replace("\\", "/"),
         "sha256": _sha256_file(os.path.join(args.study, "equal_budget_summary.json"))},
    ]
    bundle = {
        "bundle_version": "1.0.0",
        "experiment_id": manifest["experiment_id"],
        "foundry_commit": _git_head(),
        "manifest_sha256": _sha256_file(args.manifest),
        "created_utc": close_payload["created_utc"],
        "inputs": {
            "campaign": os.path.relpath(args.campaign, REPO_ROOT).replace("\\", "/"),
            "study": os.path.relpath(args.study, REPO_ROOT).replace("\\", "/"),
            "threshold_method": "eesm/docs/THRESHOLD_FREEZE_METHOD.md",
        },
        "environment": {
            "python": sys.version.split()[0],
            "working_tree_may_be_dirty": True,
        },
        "stages": {
            "fem_campaign": "complete",
            "equal_budget_fit": "complete",
            "promotion": promotion["status"],
            "scheduler_audit": None if audit is None else audit["gates"]["status"],
        },
        "decisions": {
            "promotion": {
                "status": promotion["status"],
                "candidate": promotion.get("candidate_id"),
                "family": promotion.get("family"),
                "reason": promotion.get("reason"),
            }
        },
        "artifacts": artifacts,
        "gates": {
            "threshold_status": "frozen",
            "thresholds": manifest["gates"]["thresholds"],
        },
    }
    bundle_path = out / "result_bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")

    print(json.dumps({
        "close": str(close_path),
        "bundle": str(bundle_path),
        "promotion": promotion["status"],
        "candidate": promotion.get("candidate_id"),
        "n_pass": sum(1 for run in ranking_runs if run["all_required_pass"]),
        "n_runs": len(ranking_runs),
        "audit_status": None if audit is None else audit["gates"]["status"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
