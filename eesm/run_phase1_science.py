#!/usr/bin/env python
"""Phase 1 science study: lambda_f as a third output, reciprocity, and L_diff.

What this adds over the existing Phase 1 bundle
-----------------------------------------------
`out/eesm/phase1_close_20260813/` registered `energy_gradient_net` and `pwa`
but scored them on exactly the Phase 0 axes: two outputs, eight frozen gates,
torque RMSE ranking. None of the physics that motivates a structured surrogate
was measured. This runner adds the three missing pieces:

  1. lambda_f (terminal) as a supervised third output for every family.
  2. Reciprocity residuals -- the amplitude-invariant mixed-partial identities.
  3. L_diff error against the 8 FEM finite-difference anchors.
  4. The zero-shot lambda_f ablation, with its If-only control.

What this deliberately does NOT do
----------------------------------
* It does not retune, re-derive, or re-freeze the eight thresholds. They are
  read from the manifest and applied unchanged to the stator channels.
* The new metrics are DIAGNOSTICS. They do not gate promotion. Making them
  gates requires a new pre-registered phase with its own threshold freeze.
* It does not write into any existing output root, the identity freeze, or
  `out/eesm/task9_baseline/`.
* No FEMM solve. Every number comes from the finished campaign and anchors.
"""

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

from experiments.equal_budget import (  # noqa: E402
    _derived_seed,
    _domain_from_manifest,
    _sample_matrix,
    _sample_training,
    _validate_manifest,
)
from data.femm_truth import ORIGIN_ID  # noqa: E402
from metrics import field_gauge, ldiff  # noqa: E402
from metrics import reciprocity as recip  # noqa: E402
from sampling.sample_designs import latin_hypercube_samples  # noqa: E402
from surrogates.registry import build_surrogate  # noqa: E402

FIELD_SECTOR_TO_TERMINAL = recip.FIELD_SECTOR_TO_TERMINAL
CHANNELS = ("lambda_d_wb", "lambda_q_wb", "lambda_f_terminal_wb")


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _git_is_dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT,
        check=True, capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def load_campaign(path: Path) -> dict[str, dict[str, Any]]:
    """point_id -> row, converged rows only, with terminal lambda_f attached."""
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    table: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("converged", "")).strip().lower() not in ("true", "1"):
            continue
        row["lambda_f_terminal_wb"] = (
            FIELD_SECTOR_TO_TERMINAL * float(row["lambda_field_wb"])
        )
        table[row["point_id"]] = row
    return table


def truth_matrix(table: dict[str, dict[str, Any]], ids: list[str]) -> np.ndarray:
    """(n, 3) truth for the given point ids. Fails closed on a missing id.

    The source-free origin is the one analytic row, exactly as
    `data.femm_truth.FemmCampaignTruth` treats it: no field current and no
    stator current on a machine with no magnets means all three flux linkages
    are identically zero, so it was never sent to FEMM. Every other absent
    identity is an error -- this study must not interpolate a training label.
    """
    missing = [pid for pid in ids if pid not in table and pid != ORIGIN_ID]
    if missing:
        raise SystemExit(
            f"{len(missing)} design point(s) absent from the campaign, "
            f"first={missing[0]}. Refusing to interpolate truth."
        )
    rows = []
    for pid in ids:
        if pid not in table and pid == ORIGIN_ID:
            rows.append([0.0, 0.0, 0.0])
            continue
        rows.append([
            float(table[pid]["lambda_d_wb"]),
            float(table[pid]["lambda_q_wb"]),
            float(table[pid]["lambda_f_terminal_wb"]),
        ])
    return np.array(rows, dtype=np.float64)


def torque(pole_pairs: int, flux: np.ndarray, currents: np.ndarray) -> np.ndarray:
    """Amplitude-invariant dq identity torque; never carries a sector factor."""
    return 1.5 * pole_pairs * (
        flux[:, 0] * currents[:, 1] - flux[:, 1] * currents[:, 0]
    )


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def region_of(table, ids):
    return np.array([table[pid].get("region", "interior") for pid in ids])


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--zero-shot", action="store_true",
        help="also run the stator-only lambda_f ablation and its If-only control",
    )
    args = parser.parse_args()

    out_root = Path(args.out).resolve()
    if out_root.exists() and any(out_root.iterdir()):
        raise SystemExit(f"refusing to write into a non-empty root: {out_root}")
    for forbidden in ("task9_baseline", "femm_equal_budget_points_"):
        if forbidden in str(out_root):
            raise SystemExit(f"refusing to write near a frozen root: {out_root}")
    out_root.mkdir(parents=True, exist_ok=True)

    manifest_bytes = Path(args.manifest).read_bytes()
    manifest = json.loads(manifest_bytes)
    manifest_sha = _sha256_bytes(manifest_bytes)

    gates_block = manifest["gates"]
    if gates_block.get("status") != "frozen":
        raise SystemExit("manifest gates are not frozen; refusing to run")
    thresholds = dict(gates_block["thresholds"])

    campaign_path = Path(args.campaign).resolve()
    table = load_campaign(campaign_path)
    anchors = json.loads(Path(args.anchors).read_text())
    floors = recip.fem_reciprocity_floors(anchors)

    # Reuse the frozen study's own validator so strategies, budgets, families
    # and seeds are read exactly the way the equal-budget runner reads them.
    strategies, budgets, families, seeds = _validate_manifest(manifest)
    pole_pairs = int(manifest["machine"]["pole_pairs"])
    domain = _domain_from_manifest(manifest)

    # ---- reserved roles, reproduced exactly as the frozen study does ----
    role_budget = max(budgets)
    selection_samples = latin_hypercube_samples(
        domain, n=role_budget,
        seed=_derived_seed(seeds["split"], "selection", role_budget),
    )
    selection_ids = [str(v) for v in selection_samples["point_id"]]
    selection_X = _sample_matrix(selection_samples)
    selection_Y = truth_matrix(table, selection_ids)
    selection_T = torque(pole_pairs, selection_Y, selection_X)

    print(f"selection rows: {len(selection_ids)}")
    print(f"reciprocity FEM floors: R_dq={floors['R_dq']:.3e} H  "
          f"R_fd={floors['R_fd']:.3e} H  (naive={floors['R_fd_naive']:.3e} H)")

    runs: list[dict[str, Any]] = []
    ablation: list[dict[str, Any]] = []

    for strategy in strategies:
        for budget in budgets:
            sample_seed = _derived_seed(seeds["split"], strategy, budget)
            design = _sample_training(strategy, domain, budget, sample_seed)
            train_ids = [str(v) for v in design["point_id"]]
            overlap = set(train_ids) & set(selection_ids)
            if overlap:
                raise SystemExit(f"role overlap for {strategy}|{budget}: {overlap}")
            train_X = _sample_matrix(design)
            train_Y = truth_matrix(table, train_ids)

            for family in families:
                config = dict(
                    manifest.get("surrogate_configs", {}).get(family, {})
                )
                model = build_surrogate(family, seed=int(seeds["model"]),
                                        config=config)
                model.fit(train_X, train_Y)
                pred = model.predict(selection_X)

                metrics: dict[str, Any] = {
                    "n_train": len(train_ids),
                    "n_selection": len(selection_ids),
                    "training_point_ids_sha256": _sha256_bytes(
                        "\n".join(train_ids).encode()
                    ),
                }
                for i, name in enumerate(CHANNELS[: pred.shape[1]]):
                    metrics[name] = {"rmse": rmse(pred[:, i], selection_Y[:, i])}
                metrics["torque_rmse_nm"] = rmse(
                    torque(pole_pairs, pred, selection_X), selection_T
                )
                metrics["reciprocity"] = recip.summarize(
                    recip.reciprocity_residuals(model.predict, selection_X),
                    floors=floors,
                )
                metrics["l_diff"] = ldiff.ldiff_error(model.predict, anchors)

                runs.append({
                    "candidate_id": f"{strategy}|{budget}|{family}",
                    "strategy": strategy, "budget": budget, "family": family,
                    "sample_seed": int(sample_seed),
                    "model_seed": int(seeds["model"]),
                    "metrics": metrics,
                })
                r = metrics["reciprocity"]
                print(f"  {strategy:<16} {budget:>3} {family:<20} "
                      f"lamF={metrics[CHANNELS[2]]['rmse']:.3e} "
                      f"T={metrics['torque_rmse_nm']:.4f} "
                      f"R_dq={r['R_dq']['rms_h']:.2e} "
                      f"R_fd={r['R_fd']['rms_h']:.2e} "
                      f"Ldiff={metrics['l_diff']['frobenius_rel_rmse']:.3f}")

            # ---- zero-shot lambda_f ablation ----
            if args.zero_shot:
                zs_model = build_surrogate(
                    "energy_gradient_net", seed=int(seeds["model"]),
                    config={"field_supervision": False},
                )
                zs_model.fit(train_X, train_Y[:, :2])
                # Same architecture and epochs as the supervised run, so the
                # only difference is whether lambda_f was supervised. Recording
                # the stator metrics here makes "does the free field side
                # channel improve the stator map?" a controlled comparison
                # rather than a confound with network size.
                zs_pred = zs_model.predict(selection_X)
                zs_stator = {
                    "lambda_d_wb_rmse": rmse(zs_pred[:, 0], selection_Y[:, 0]),
                    "lambda_q_wb_rmse": rmse(zs_pred[:, 1], selection_Y[:, 1]),
                    "torque_rmse_nm": rmse(
                        torque(pole_pairs, zs_pred, selection_X), selection_T
                    ),
                }
                raw_tr = zs_model.predict_field(train_X)
                raw_se = zs_model.predict_field(selection_X)
                gauge = field_gauge.fit_gauge(
                    train_X[:, 2], raw_tr, train_Y[:, 2]
                )
                corrected = gauge.apply(raw_se, selection_X[:, 2])
                control = field_gauge.field_only_control(
                    train_X[:, 2], train_Y[:, 2], selection_X[:, 2]
                )
                entry = {
                    "candidate_id": f"{strategy}|{budget}|energy_gradient_net_zeroshot",
                    "strategy": strategy, "budget": budget,
                    "lambda_f_rmse_uncalibrated": rmse(raw_se, selection_Y[:, 2]),
                    "lambda_f_rmse_gauge_fixed": rmse(corrected, selection_Y[:, 2]),
                    "lambda_f_rmse_if_only_control": rmse(control, selection_Y[:, 2]),
                    "lambda_f_rmse_mean_baseline": rmse(
                        np.full(len(selection_Y), train_Y[:, 2].mean()),
                        selection_Y[:, 2],
                    ),
                    "lambda_f_truth_std": float(selection_Y[:, 2].std()),
                    "gauge_dimensionality_r2_oos": field_gauge.gauge_dimensionality_r2(
                        gauge, selection_X[:, 2], raw_se, selection_Y[:, 2]
                    ),
                    "gauge": gauge.to_dict(),
                    "stator_metrics_unsupervised_field": zs_stator,
                }
                entry["control_ratio"] = (
                    entry["lambda_f_rmse_if_only_control"]
                    / entry["lambda_f_rmse_gauge_fixed"]
                )
                ablation.append(entry)
                print(f"  {strategy:<16} {budget:>3} ZERO-SHOT lambda_f: "
                      f"gauge_fixed={entry['lambda_f_rmse_gauge_fixed']:.3e} "
                      f"if_only={entry['lambda_f_rmse_if_only_control']:.3e} "
                      f"({entry['control_ratio']:.1f}x better)  "
                      f"R2={entry['gauge_dimensionality_r2_oos']:.4f}")

    created = datetime.now(timezone.utc).isoformat()
    study = {
        "created_utc": created,
        "experiment_id": manifest["experiment_id"],
        "manifest_sha256": manifest_sha,
        "campaign": str(campaign_path),
        "campaign_sha256": _sha256_file(campaign_path),
        "anchors": str(Path(args.anchors).resolve()),
        "anchors_sha256": _sha256_file(args.anchors),
        "reciprocity_fem_floors_h": floors,
        "frozen_thresholds": thresholds,
        "threshold_note": (
            "Read from the manifest and applied unchanged. Reciprocity and "
            "L_diff are diagnostics in this phase and gate nothing."
        ),
        "runs": runs,
        "zero_shot_ablation": ablation,
    }
    study_path = out_root / "phase1_science.json"
    study_path.write_text(json.dumps(study, indent=1, sort_keys=True))

    bundle = {
        "bundle_version": "1.0.0",
        "experiment_id": manifest["experiment_id"],
        "created_utc": created,
        "foundry_commit": _git_head(),
        "manifest_sha256": manifest_sha,
        "environment": {
            "python": sys.version.split()[0],
            "working_tree_may_be_dirty": _git_is_dirty(),
            "git_dirty": _git_is_dirty(),
        },
        "inputs": {
            "campaign": str(campaign_path),
            "anchors": str(Path(args.anchors).resolve()),
        },
        "stages": {
            "equal_budget_fit": "complete",
            "reciprocity_diagnostic": "complete",
            "l_diff_diagnostic": "complete",
            "zero_shot_field_ablation": "complete" if ablation else "skipped",
        },
        "decisions": {
            "promotion": {
                "status": "not_attempted",
                "candidate": None,
                "reason": (
                    "diagnostic phase; promotion stays with the frozen "
                    "Phase 1 bundle"
                ),
            }
        },
        "gates": {
            "threshold_status": "frozen",
            "thresholds": thresholds,
            "diagnostics_are_not_gates": True,
        },
        "artifacts": [
            {"path": os.path.relpath(study_path, REPO_ROOT).replace("\\", "/"),
             "sha256": _sha256_file(study_path)},
        ],
    }
    (out_root / "result_bundle.json").write_text(
        json.dumps(bundle, indent=1, sort_keys=True)
    )
    print(f"\nwrote {study_path}")
    print(f"wrote {out_root / 'result_bundle.json'}")
    if bundle["environment"]["working_tree_may_be_dirty"]:
        print("WARNING: working tree is dirty; commit before treating this "
              "bundle as evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
