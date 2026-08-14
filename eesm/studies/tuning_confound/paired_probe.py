"""Paired fix: LML-optimized GP vs seed-median compact MLP.

Phase 0 handicapped BOTH models in opposite directions -- the GP never fitted
its kernel, and MLP seed 1701 turned out to be a bad draw. Fixing one alone
biases the comparison. This fixes both at once, on the exact frozen training
designs and the frozen 256-point selection set.

Sensitivity analysis. The Phase 0 bundle is unchanged by anything here.
"""
import csv, json, os, sys, warnings
import numpy as np

warnings.filterwarnings("ignore")
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eesm", "src")
sys.path.insert(0, SRC)

from experiments.equal_budget import (  # noqa: E402
    _derived_seed, _domain_from_manifest, _sample_matrix, _sample_training,
    _validate_manifest,
)
from sampling.sample_designs import latin_hypercube_samples  # noqa: E402
from surrogates.registry import build_surrogate  # noqa: E402
from data.femm_truth import ORIGIN_ID  # noqa: E402

manifest = json.loads(open("eesm/configs/eesm_experiment_manifest.json").read())
strategies, budgets, families, seeds = _validate_manifest(manifest)
domain = _domain_from_manifest(manifest)
P = int(manifest["machine"]["pole_pairs"])
N_SEEDS = 8

table = {r["point_id"]: r for r in
         csv.DictReader(open("out/eesm/femm_equal_budget_20260813/femm_results.csv",
                             newline=""))
         if str(r["converged"]).lower() in ("true", "1")}


def truth(ids):
    out = []
    for pid in ids:
        if pid == ORIGIN_ID and pid not in table:
            out.append([0.0, 0.0]); continue
        r = table[pid]
        out.append([float(r["lambda_d_wb"]), float(r["lambda_q_wb"])])
    return np.array(out)


def torque(f, c):
    return 1.5 * P * (f[:, 0] * c[:, 1] - f[:, 1] * c[:, 0])


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


rb = max(budgets)
sel = latin_hypercube_samples(domain, n=rb,
                              seed=_derived_seed(seeds["split"], "selection", rb))
selX, selY = _sample_matrix(sel), truth([str(v) for v in sel["point_id"]])
selT = torque(selY, selX)

GP_OPT = {"optimizer": "fmin_l_bfgs_b", "n_restarts_optimizer": 5}
# seed family for the MLP: the frozen seed plus 7 derived, so 1701 stays in the set
SEEDS = [1701] + [_derived_seed(1701, "mlp", i) % (2**31) for i in range(N_SEEDS - 1)]

rows = {}
print(f"{'cell':<22}{'GPfroz':>8}{'GPopt':>8}{'MLP1701':>9}"
      f"{'MLPmed':>8}{'MLPq25':>8}{'MLPq75':>8}   winner(paired)")
for strategy in strategies:
    for b in budgets:
        ss = _derived_seed(seeds["split"], strategy, b)
        d = _sample_training(strategy, domain, b, ss)
        X, Y = _sample_matrix(d), truth([str(v) for v in d["point_id"]])

        gp_f = build_surrogate("rbf_or_gp", seed=1701, config={}).fit(X, Y)
        gp_o = build_surrogate("rbf_or_gp", seed=1701, config=GP_OPT).fit(X, Y)
        t_gf = rmse(torque(gp_f.predict(selX), selX), selT)
        t_go = rmse(torque(gp_o.predict(selX), selX), selT)

        mlps = []
        for s in SEEDS:
            m = build_surrogate("compact_mlp", seed=int(s), config={}).fit(X, Y)
            mlps.append(rmse(torque(m.predict(selX), selX), selT))
        mlps = np.array(mlps)
        med, q25, q75 = np.median(mlps), np.percentile(mlps, 25), np.percentile(mlps, 75)
        win = "GP" if t_go < med else "MLP"
        rows[f"{strategy}|{b}"] = {
            "gp_frozen": t_gf, "gp_opt": t_go, "mlp_seed1701": float(mlps[0]),
            "mlp_median": float(med), "mlp_q25": float(q25), "mlp_q75": float(q75),
            "mlp_all": [float(v) for v in mlps], "paired_winner": win,
            "gp_inside_mlp_iqr": bool(q25 <= t_go <= q75),
        }
        print(f"{strategy+'|'+str(b):<22}{t_gf:>8.4f}{t_go:>8.4f}{mlps[0]:>9.4f}"
              f"{med:>8.4f}{q25:>8.4f}{q75:>8.4f}   {win}")

print()
for b in budgets:
    cells = {k: v for k, v in rows.items() if k.endswith(f"|{b}")}
    bg = min(cells.items(), key=lambda kv: kv[1]["gp_opt"])
    bm = min(cells.items(), key=lambda kv: kv[1]["mlp_median"])
    overall = "GP" if bg[1]["gp_opt"] < bm[1]["mlp_median"] else "MLP"
    print(f"budget {b:>3}: best GPopt {bg[0]} {bg[1]['gp_opt']:.4f} | "
          f"best MLPmed {bm[0]} {bm[1]['mlp_median']:.4f}  -> {overall}")

json.dump({"n_seeds": N_SEEDS, "seeds": [int(s) for s in SEEDS], "cells": rows},
          open("/home/claude/paired_probe.json", "w"), indent=1)
print("\nwrote /home/claude/paired_probe.json")
