"""Does the unoptimized GP kernel change the Phase 0 conclusion?

Uses the repository's own RBFOrGPSurrogate with config overrides, on the exact
frozen training designs and the frozen 256-point selection set. This is a
SENSITIVITY ANALYSIS, not a modification of the frozen experiment: the Phase 0
bundle stands regardless of what this prints.
"""
import json, os, sys, warnings
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

import csv
CAMP = "out/eesm/femm_equal_budget_20260813/femm_results.csv"
MAN = "eesm/configs/eesm_experiment_manifest.json"

manifest = json.loads(open(MAN).read())
strategies, budgets, families, seeds = _validate_manifest(manifest)
domain = _domain_from_manifest(manifest)
P = int(manifest["machine"]["pole_pairs"])

table = {}
for row in csv.DictReader(open(CAMP, newline="")):
    if str(row["converged"]).lower() in ("true", "1"):
        table[row["point_id"]] = row


def truth(ids):
    out = []
    for pid in ids:
        if pid == ORIGIN_ID and pid not in table:
            out.append([0.0, 0.0]); continue
        r = table[pid]
        out.append([float(r["lambda_d_wb"]), float(r["lambda_q_wb"])])
    return np.array(out)


def torque(flux, cur):
    return 1.5 * P * (flux[:, 0] * cur[:, 1] - flux[:, 1] * cur[:, 0])


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


rb = max(budgets)
sel = latin_hypercube_samples(domain, n=rb,
                              seed=_derived_seed(seeds["split"], "selection", rb))
selX = _sample_matrix(sel)
selY = truth([str(v) for v in sel["point_id"]])
selT = torque(selY, selX)

VARIANTS = {
    "A frozen (optimizer=None)": {},
    "B iso + LML opt": {"optimizer": "fmin_l_bfgs_b", "n_restarts_optimizer": 5},
    "C ARD + LML opt": {"optimizer": "fmin_l_bfgs_b", "n_restarts_optimizer": 5,
                        "length_scale": [1.0, 1.0, 1.0]},
}

res = {}
print(f"{'cell':<28}" + "".join(f"{k.split()[0]:>10}" for k in VARIANTS))
for strategy in strategies:
    for b in budgets:
        ss = _derived_seed(seeds["split"], strategy, b)
        d = _sample_training(strategy, domain, b, ss)
        ids = [str(v) for v in d["point_id"]]
        X, Y = _sample_matrix(d), truth(ids)
        row = {}
        for name, cfg in VARIANTS.items():
            m = build_surrogate("rbf_or_gp", seed=int(seeds["model"]), config=cfg)
            m.fit(X, Y)
            pred = m.predict(selX)
            row[name] = {"torque_rmse_nm": rmse(torque(pred, selX), selT),
                         "flux_rmse_wb": rmse(pred, selY),
                         "kernel": str(m.model_.kernel_)}
        res[f"{strategy}|{b}"] = row
        print(f"{strategy+'|'+str(b):<28}" +
              "".join(f"{row[k]['torque_rmse_nm']:>10.4f}" for k in VARIANTS))

print("\nfitted kernels at latin_hypercube|256:")
for k in VARIANTS:
    print(f"  {k:<26} {res['latin_hypercube|256'][k]['kernel']}")

json.dump(res, open("/home/claude/gp_probe.json", "w"), indent=1)
print("\nwrote /home/claude/gp_probe.json")
