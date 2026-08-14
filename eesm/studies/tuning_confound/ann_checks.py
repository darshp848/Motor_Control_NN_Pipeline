"""Three checks on the sweep before any of it is believed.

1. Was the Phase 0 MLP simply undertrained? Sweep the epoch budget.
2. The reciprocity penalty produced results identical to no penalty -- is the
   penalty numerically negligible rather than useless?
3. Fourier features scored 15-26 N.m, worse than predicting zero. Bandwidth bug
   or genuine failure?
"""
import csv, json, os, sys, warnings
import numpy as np
import torch
from torch import nn

warnings.filterwarnings("ignore")
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eesm", "src")
sys.path.insert(0, SRC)
from experiments.equal_budget import (  # noqa: E402
    _derived_seed, _domain_from_manifest, _sample_matrix, _sample_training,
    _validate_manifest)
from sampling.sample_designs import latin_hypercube_samples  # noqa: E402
from surrogates.registry import build_surrogate  # noqa: E402
from data.femm_truth import ORIGIN_ID  # noqa: E402

manifest = json.loads(open("eesm/configs/eesm_experiment_manifest.json").read())
strategies, budgets, families, seeds = _validate_manifest(manifest)
domain = _domain_from_manifest(manifest)
P = int(manifest["machine"]["pole_pairs"])
table = {r["point_id"]: r for r in csv.DictReader(
    open("out/eesm/femm_equal_budget_20260813/femm_results.csv", newline=""))
    if str(r["converged"]).lower() in ("true", "1")}


def truth(ids):
    o = []
    for pid in ids:
        if pid == ORIGIN_ID and pid not in table:
            o.append([0.0, 0.0]); continue
        r = table[pid]; o.append([float(r["lambda_d_wb"]), float(r["lambda_q_wb"])])
    return np.array(o)


def torque(f, c): return 1.5 * P * (f[:, 0] * c[:, 1] - f[:, 1] * c[:, 0])
def rmse(a, b): return float(np.sqrt(np.mean((a - b) ** 2)))


rb = max(budgets)
sel = latin_hypercube_samples(domain, n=rb,
                              seed=_derived_seed(seeds["split"], "selection", rb))
selX, selY = _sample_matrix(sel), truth([str(v) for v in sel["point_id"]])
selT = torque(selY, selX)


def design(strategy, b):
    d = _sample_training(strategy, domain, b, _derived_seed(seeds["split"], strategy, b))
    return _sample_matrix(d), truth([str(v) for v in d["point_id"]])


# ---------------------------------------------------------------- check 1
print("CHECK 1 -- epoch sweep for the Phase 0 compact MLP (median of 3 seeds)")
print(f"{'cell':<20}" + "".join(f"{e:>10}" for e in (300, 600, 1200, 2400, 4800)))
for strategy, b in (("tensor_grid", 64), ("random", 256), ("latin_hypercube", 256)):
    X, Y = design(strategy, b)
    row = []
    for ep in (300, 600, 1200, 2400, 4800):
        v = []
        for k in range(3):
            m = build_surrogate("compact_mlp", seed=1701 + 104729 * k,
                                config={"epochs": ep})
            m.fit(X, Y)
            v.append(rmse(torque(m.predict(selX), selX), selT))
        row.append(np.median(v))
    print(f"{strategy+'|'+str(b):<20}" + "".join(f"{r:>10.4f}" for r in row))

# ---------------------------------------------------------------- check 2
print("\nCHECK 2 -- magnitude of the reciprocity penalty vs the data term")
X, Y = design("latin_hypercube", 256)
xm, xs = X.mean(0), X.std(0); ym, ys = Y.mean(0), Y.std(0)
Xn, Yn = (X - xm) / xs, (Y - ym) / ys
torch.manual_seed(1701)
net = nn.Sequential(nn.Linear(3, 32), nn.Tanh(), nn.Linear(32, 32), nn.Tanh(),
                    nn.Linear(32, 2)).to(dtype=torch.float64)
Xt = torch.as_tensor(Xn, dtype=torch.float64); Yt = torch.as_tensor(Yn, dtype=torch.float64)
opt = torch.optim.Adam(net.parameters(), lr=0.01)
for _ in range(600):
    opt.zero_grad(); nn.functional.mse_loss(net(Xt), Yt).backward(); opt.step()
data_term = float(nn.functional.mse_loss(net(Xt), Yt))
xin = Xt.clone().requires_grad_(True); out = net(xin)
gd = torch.autograd.grad(out[:, 0].sum(), xin, create_graph=True)[0]
gq = torch.autograd.grad(out[:, 1].sum(), xin, create_graph=True)[0]
xst = torch.as_tensor(xs); yst = torch.as_tensor(ys)
resid = gd[:, 1] * yst[0] / xst[1] - gq[:, 0] * yst[1] / xst[0]
pen_term = float((resid ** 2).mean())
print(f"  data MSE (normalized targets) : {data_term:.3e}")
print(f"  reciprocity penalty at w=1     : {pen_term:.3e}")
print(f"  ratio penalty/data             : {pen_term/data_term:.3e}")
print(f"  -> w=1 is numerically inert; a comparable weight is w ~ {data_term/pen_term:.3g}")

# ---------------------------------------------------------------- check 3
print("\nCHECK 3 -- Fourier-feature bandwidth sweep (median of 3 seeds, lhs|256)")
X, Y = design("latin_hypercube", 256)
xm, xs = X.mean(0), X.std(0); ym, ys = Y.mean(0), Y.std(0)
Xn, Yn = (X - xm) / xs, (Y - ym) / ys
Sn = (selX - xm) / xs
for scale in (0.01, 0.03, 0.1, 0.3, 0.6):
    v = []
    for k in range(3):
        g = torch.Generator().manual_seed(1701 + 104729 * k)
        torch.manual_seed(1701 + 104729 * k)
        B = torch.randn(3, 32, generator=g, dtype=torch.float64) * scale

        class Enc(nn.Module):
            def forward(self, x):
                p = 2.0 * np.pi * x @ B
                return torch.cat([torch.sin(p), torch.cos(p)], -1)

        net = nn.Sequential(Enc(), nn.Linear(64, 64), nn.Tanh(),
                            nn.Linear(64, 64), nn.Tanh(),
                            nn.Linear(64, 2)).to(dtype=torch.float64)
        Xt = torch.as_tensor(Xn); Yt = torch.as_tensor(Yn)
        opt = torch.optim.Adam(net.parameters(), lr=0.01)
        for _ in range(600):
            opt.zero_grad(); nn.functional.mse_loss(net(Xt), Yt).backward(); opt.step()
        with torch.no_grad():
            pred = net(torch.as_tensor(Sn)).numpy() * ys + ym
        v.append(rmse(torque(pred, selX), selT))
    print(f"  rff_scale {scale:<6} torque RMSE {np.median(v):.4f}")
