#!/usr/bin/env python
"""Equal-tuning-budget family comparison.

Protocol: eesm/docs/EQUAL_TUNING_PROTOCOL.md (declared before this ran).

Every family gets the SAME number of configuration evaluations, drawn from its
declared search space, scored by k-fold cross-validation on the TRAINING DESIGN
ONLY. The selection set is used exactly once per cell, after the configuration
is chosen. The winner is refitted over several model seeds and reported as a
median with an interquartile range.

This is a new experiment. It does not modify, re-derive or re-freeze anything
in Phase 0 or Phase 1, and it promotes nothing.
"""

from __future__ import annotations

import argparse
import concurrent.futures as _cf
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

from data.femm_truth import ORIGIN_ID  # noqa: E402
from experiments.equal_budget import (  # noqa: E402
    _derived_seed, _domain_from_manifest, _sample_matrix, _sample_training,
    _validate_manifest,
)
from sampling.sample_designs import latin_hypercube_samples  # noqa: E402
from surrogates.registry import build_surrogate  # noqa: E402


# ----------------------------------------------------------------------
def _sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as s:
        for b in iter(lambda: s.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def _git(*args: str) -> str | None:
    """Git metadata, or None where git is unavailable.

    Never fatal: a missing repository must not discard a completed run. A None
    commit is recorded honestly so the bundle cannot be mistaken for one with
    verified provenance.
    """
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return None


def sample_config(space: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    """Draw one configuration from a declared space."""
    cfg: dict[str, Any] = {}
    for key, spec in space.items():
        if not isinstance(spec, dict):
            cfg[key] = spec                       # fixed value
        elif spec.get("type") == "choice":
            cfg[key] = spec["values"][int(rng.integers(len(spec["values"])))]
        elif spec.get("type") == "loguniform":
            lo, hi = np.log10(spec["low"]), np.log10(spec["high"])
            cfg[key] = float(10.0 ** rng.uniform(lo, hi))
        else:
            raise ValueError(f"unknown spec for {key}: {spec}")
    # ARD is expressed through length_scale, not as its own kwarg
    if cfg.pop("ard", False):
        ls = cfg.get("length_scale", 1.0)
        cfg["length_scale"] = [float(ls)] * 3
    return cfg


def enumerate_space_size(space: dict[str, Any]) -> float:
    n = 1.0
    for spec in space.values():
        if isinstance(spec, dict):
            if spec.get("type") == "choice":
                n *= len(spec["values"])
            else:
                return float("inf")            # continuous
    return n


def config_key(cfg: dict[str, Any]) -> str:
    return json.dumps(cfg, sort_keys=True, default=str)


def kfold_indices(n: int, k: int, seed: int) -> list[np.ndarray]:
    idx = np.random.default_rng(seed).permutation(n)
    return [np.sort(f) for f in np.array_split(idx, k)]



def parse_cpu_list(spec: str) -> list[int]:
    """Parse "8-19" / "0,2,4" / "8-11,16-19" into a sorted list of logical CPUs."""
    out: set[int] = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            lo, hi = int(lo), int(hi)
            if hi < lo:
                raise ValueError(f"bad cpu range: {part}")
            out.update(range(lo, hi + 1))
        else:
            out.add(int(part))
    if not out:
        raise ValueError(f"no CPUs parsed from {spec!r}")
    return sorted(out)


def apply_cpu_placement(cpus: list[int] | None, priority: str | None) -> dict[str, Any]:
    """Pin this process to `cpus` and set its scheduling priority.

    Placement is a scheduling concern only: every fit is single-threaded and
    independently seeded, so which core runs it cannot change a result. The
    chosen placement is recorded in the bundle because it is part of the
    compute environment, not because it affects the numbers.

    Degrades to a no-op with an explanatory record if psutil is unavailable.
    """
    record: dict[str, Any] = {"requested_cpus": cpus, "requested_priority": priority}
    if cpus is None and priority is None:
        return record
    try:
        import psutil
    except ImportError:
        record["applied"] = False
        record["reason"] = "psutil not installed; run unpinned or pip install psutil"
        return record
    proc = psutil.Process()
    try:
        if cpus is not None:
            proc.cpu_affinity(cpus)
            record["effective_cpus"] = proc.cpu_affinity()
        if priority is not None:
            levels = {
                "idle": getattr(psutil, "IDLE_PRIORITY_CLASS", 19),
                "below-normal": getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", 10),
                "normal": getattr(psutil, "NORMAL_PRIORITY_CLASS", 0),
            }
            if priority not in levels:
                raise ValueError(f"unknown priority {priority!r}")
            proc.nice(levels[priority])
            record["effective_priority"] = str(proc.nice())
        record["applied"] = True
    except Exception as exc:                      # never fatal
        record["applied"] = False
        record["reason"] = f"{type(exc).__name__}: {exc}"
    return record


def _worker_init(cpus: list[int] | None, priority: str | None) -> None:
    """Re-apply placement inside each worker, for spawn contexts that do not
    inherit the parent's affinity."""
    apply_cpu_placement(cpus, priority)


def _score_config(task):
    """Inner CV score for one configuration. Module level so it is picklable.

    Returns None when the family rejects the configuration -- an unfittable draw
    is skipped, not scored, and the shortfall is visible in n_configs_effective.
    """
    family, model_seed, cfg, ci, X, Y, folds, pole_pairs = task
    import numpy as _np

    def _t(f, c):
        return 1.5 * pole_pairs * (f[:, 0] * c[:, 1] - f[:, 1] * c[:, 0])

    def _r(a, b):
        return float(_np.sqrt(_np.mean((_np.asarray(a) - _np.asarray(b)) ** 2)))

    scores = []
    for f in folds:
        mask = _np.ones(len(X), bool); mask[f] = False
        if mask.sum() < 4 or len(f) < 2:
            return None
        try:
            m = build_surrogate(family, seed=model_seed, config=dict(cfg))
            m.fit(X[mask], Y[mask])
            p = m.predict(X[f])
        except Exception:
            return None
        scores.append((_r(_t(p, X[f]), _t(Y[f], X[f])), _r(p, Y[f])))
    if not scores:
        return None
    return {"index": ci, "config": cfg,
            "inner_torque_rmse_nm": float(_np.mean([s[0] for s in scores])),
            "inner_flux_rmse_wb": float(_np.mean([s[1] for s in scores]))}


# ----------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--smoke", action="store_true",
                    help="reduced budget for a plumbing check; not authoritative")
    ap.add_argument("--workers", type=int, default=1,
                    help=("parallel worker processes for the inner CV. The 3888 "
                          "inner fits are independent and each is seeded, so this "
                          "changes wall time only, never a number."))
    ap.add_argument("--cpu-affinity", default=None, metavar="SPEC",
                    help=("logical CPUs to run on, e.g. '8-19'. Use this to keep "
                          "the run off cores another job needs. On an Intel "
                          "hybrid part the efficient cores are the high-numbered "
                          "ones; see EQUAL_TUNING_PROTOCOL.md."))
    ap.add_argument("--priority", default=None,
                    choices=["idle", "below-normal", "normal"],
                    help="scheduling priority; below-normal yields to a foreground job")
    args = ap.parse_args()

    print(f"interpreter: {sys.executable}")
    cpus = parse_cpu_list(args.cpu_affinity) if args.cpu_affinity else None
    placement = apply_cpu_placement(cpus, args.priority)
    if cpus is not None or args.priority is not None:
        print(f"cpu placement: {placement}")
        if not placement.get("applied"):
            print(f"  WARNING: placement NOT applied -- {placement.get('reason')}")

    out_root = Path(args.out).resolve()
    for forbidden in ("task9_baseline", "femm_equal_budget_points_"):
        if forbidden in str(out_root):
            raise SystemExit(f"refusing to write near a frozen root: {out_root}")
    if out_root.exists() and any(out_root.iterdir()):
        raise SystemExit(f"refusing to write into a non-empty root: {out_root}")
    out_root.mkdir(parents=True, exist_ok=True)

    manifest_bytes = Path(args.manifest).read_bytes()
    manifest = json.loads(manifest_bytes)
    tuning = manifest["tuning"]
    if manifest["gates"].get("status") != "frozen":
        raise SystemExit("manifest gates are not frozen; refusing to run")

    n_configs = 4 if args.smoke else int(tuning["n_configs"])
    k_inner = 2 if args.smoke else int(tuning["k_inner"])
    n_seeds = 2 if args.smoke else int(tuning["n_seeds"])
    spaces = tuning["search_spaces"]

    strategies, budgets, families, seeds = _validate_manifest(manifest)
    domain = _domain_from_manifest(manifest)
    P = int(manifest["machine"]["pole_pairs"])

    camp = Path(args.campaign).resolve()
    table = {r["point_id"]: r for r in csv.DictReader(open(camp, newline=""))
             if str(r["converged"]).strip().lower() in ("true", "1")}

    def truth(ids: list[str]) -> np.ndarray:
        rows = []
        for pid in ids:
            if pid == ORIGIN_ID and pid not in table:
                rows.append([0.0, 0.0]); continue
            if pid not in table:
                raise SystemExit(f"no campaign truth for {pid}; refusing to interpolate")
            r = table[pid]
            rows.append([float(r["lambda_d_wb"]), float(r["lambda_q_wb"])])
        return np.array(rows, dtype=np.float64)

    def torque(f, c):
        return 1.5 * P * (f[:, 0] * c[:, 1] - f[:, 1] * c[:, 0])

    def rmse(a, b):
        return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))

    rb = max(budgets)
    sel = latin_hypercube_samples(
        domain, n=rb, seed=_derived_seed(seeds["split"], "selection", rb))
    sel_ids = [str(v) for v in sel["point_id"]]
    selX, selY = _sample_matrix(sel), truth(sel_ids)
    selT = torque(selY, selX)

    # One pool for the whole run. Creating one per cell would pay 54 process
    # spin-ups for no benefit.
    pool = (_cf.ProcessPoolExecutor(max_workers=args.workers,
                                    initializer=_worker_init,
                                    initargs=(cpus, args.priority))
            if args.workers > 1 else None)
    results: list[dict[str, Any]] = []
    for strategy in strategies:
        for budget in budgets:
            ss = _derived_seed(seeds["split"], strategy, budget)
            design = _sample_training(strategy, domain, budget, ss)
            tr_ids = [str(v) for v in design["point_id"]]
            overlap = set(tr_ids) & set(sel_ids)
            if overlap:
                raise SystemExit(f"role overlap {strategy}|{budget}: {sorted(overlap)[:3]}")
            X, Y = _sample_matrix(design), truth(tr_ids)
            folds = kfold_indices(len(X), k_inner, _derived_seed(ss, "inner", k_inner))

            for family in families:
                space = spaces.get(family, {})
                rng = np.random.default_rng(_derived_seed(ss, "hpo", family))
                # draw distinct configurations, honouring a small finite space
                cap = enumerate_space_size(space)
                target = int(min(n_configs, cap)) if np.isfinite(cap) else n_configs
                target = max(target, 1)
                cfgs, seen = [], set()
                guard = 0
                while len(cfgs) < target and guard < 400 * target:
                    guard += 1
                    c = sample_config(space, rng)
                    k = config_key(c)
                    if k not in seen:
                        seen.add(k); cfgs.append(c)

                task = [(family, int(seeds["model"]), dict(cfg), ci, X, Y, folds, P)
                        for ci, cfg in enumerate(cfgs)]
                if pool is not None:
                    raw = list(pool.map(_score_config, task))
                else:
                    raw = [_score_config(t) for t in task]
                scored = [r for r in raw if r is not None]
                for r in scored:
                    r["config"] = cfgs[r["index"]]
                if not scored:
                    raise SystemExit(f"no configuration was fittable for {family}")
                # deterministic tie-break: torque, then flux, then draw order
                scored.sort(key=lambda s: (s["inner_torque_rmse_nm"],
                                           s["inner_flux_rmse_wb"], s["index"]))
                best = scored[0]

                outer = []
                for si in range(n_seeds):
                    sd = int(_derived_seed(seeds["model"], "refit", si) % (2 ** 31))
                    m = build_surrogate(family, seed=sd, config=dict(best["config"]))
                    m.fit(X, Y)
                    p = m.predict(selX)
                    outer.append({"seed": sd,
                                  "torque_rmse_nm": rmse(torque(p, selX), selT),
                                  "flux_rmse_wb": rmse(p, selY)})
                t = np.array([o["torque_rmse_nm"] for o in outer])
                rec = {
                    "cell": f"{strategy}|{budget}|{family}",
                    "strategy": strategy, "budget": budget, "family": family,
                    "n_configs_requested": n_configs,
                    "n_configs_effective": len(cfgs),
                    "budget_shortfall": len(cfgs) < n_configs,
                    "space_size": (None if not np.isfinite(cap) else cap),
                    "selected_config": best["config"],
                    "inner_torque_rmse_nm": best["inner_torque_rmse_nm"],
                    "outer_seeds": outer,
                    "torque_rmse_median_nm": float(np.median(t)),
                    "torque_rmse_q25_nm": float(np.percentile(t, 25)),
                    "torque_rmse_q75_nm": float(np.percentile(t, 75)),
                }
                results.append(rec)
                print(f"  {rec['cell']:<44} inner {best['inner_torque_rmse_nm']:.4f} "
                      f"| median {rec['torque_rmse_median_nm']:.4f} "
                      f"[{rec['torque_rmse_q25_nm']:.4f},{rec['torque_rmse_q75_nm']:.4f}]"
                      f"{'  (SHORTFALL)' if rec['budget_shortfall'] else ''}")

    if pool is not None:
        pool.shutdown(wait=True)

    created = datetime.now(timezone.utc).isoformat()
    study = {
        "created_utc": created,
        "experiment_id": manifest["experiment_id"],
        "smoke": bool(args.smoke),
        "protocol": "eesm/docs/EQUAL_TUNING_PROTOCOL.md",
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "campaign": str(camp), "campaign_sha256": _sha256_file(camp),
        "tuning": {"n_configs": n_configs, "k_inner": k_inner, "n_seeds": n_seeds,
                   "workers": int(args.workers)},
        "cpu_placement": placement,
        "frozen_thresholds": manifest["gates"]["thresholds"],
        "note": ("Thresholds are read unchanged and gate nothing here. This "
                 "experiment promotes nothing and modifies no frozen result."),
        "results": results,
    }
    (out_root / "equal_tuning.json").write_text(json.dumps(study, indent=1,
                                                           sort_keys=True))
    bundle = {
        "bundle_version": "1.0.0",
        "experiment_id": manifest["experiment_id"],
        "created_utc": created,
        "foundry_commit": _git("rev-parse", "HEAD"),
        "environment": {
            "python": sys.version.split()[0],
            # which interpreter produced this matters: the repo has a .venv with
            # the pinned stack, and a bare `python` on PATH is a different one
            "executable": sys.executable,
            # None means git was unavailable, which is NOT the same as clean
            "working_tree_may_be_dirty": (
                None if (_status := _git("status", "--porcelain")) is None
                else bool(_status)
            ),
        },
        "manifest_sha256": study["manifest_sha256"],
        "inputs": {"campaign": str(camp)},
        "stages": {"equal_tuning": "smoke" if args.smoke else "complete"},
        "decisions": {"promotion": {"status": "not_attempted",
                                    "reason": "tuning-fairness study"}},
        "gates": {"threshold_status": "frozen",
                  "thresholds": manifest["gates"]["thresholds"],
                  "diagnostics_are_not_gates": True},
        "artifacts": [{"path": "equal_tuning.json",
                       "sha256": _sha256_file(out_root / "equal_tuning.json")}],
    }
    (out_root / "result_bundle.json").write_text(json.dumps(bundle, indent=1,
                                                            sort_keys=True))
    print(f"\nwrote {out_root/'equal_tuning.json'}")
    if args.smoke:
        print("SMOKE RUN -- reduced budget, not an authoritative result.")
    dirty = bundle["environment"]["working_tree_may_be_dirty"]
    if dirty is None:
        print("WARNING: git unavailable; provenance unverified for this bundle.")
    elif dirty:
        print("WARNING: working tree dirty; commit before citing this bundle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
