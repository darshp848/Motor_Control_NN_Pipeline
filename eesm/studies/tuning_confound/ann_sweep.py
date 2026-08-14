"""Architecture sweep: can other ANN families beat the compact MLP here?

Every architecture subclasses the repository's FluxSurrogate, so input/output
standardization, shape validation and seeding are identical to Phase 0 and the
comparison is architecture-only. All get the SAME optimizer, learning rate and
epoch budget (except `mlp_300`, kept at the frozen Phase 0 setting for
reference), and all predict two outputs on the frozen designs and selection set.

Exploratory. Adds no family to any frozen experiment.
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
    _validate_manifest,
)
from sampling.sample_designs import latin_hypercube_samples  # noqa: E402
from surrogates.base import FluxSurrogate  # noqa: E402
from surrogates.registry import build_surrogate  # noqa: E402
from data.femm_truth import ORIGIN_ID  # noqa: E402

EPOCHS, LR, SEEDS_PER = 600, 0.01, 3


def _train(model, X, Y, epochs=EPOCHS, lr=LR, extra_loss=None):
    Xt = torch.as_tensor(X, dtype=torch.float64)
    Yt = torch.as_tensor(Y, dtype=torch.float64)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    for _ in range(epochs):
        opt.zero_grad()
        loss = nn.functional.mse_loss(model(Xt), Yt)
        if extra_loss is not None:
            loss = loss + extra_loss(model, Xt)
        loss.backward()
        opt.step()
    model.eval()
    return model


class _Torch(FluxSurrogate):
    def _predict_normalized(self, X):
        with torch.no_grad():
            return self.net_(torch.as_tensor(X, dtype=torch.float64)).cpu().numpy()


class MLP600(_Torch):
    """Same shape as the Phase 0 compact MLP, longer training."""
    family = "mlp_600"

    def _fit_normalized(self, X, y):
        torch.manual_seed(self.seed)
        self.net_ = nn.Sequential(nn.Linear(3, 32), nn.Tanh(),
                                  nn.Linear(32, 32), nn.Tanh(),
                                  nn.Linear(32, 2)).to(dtype=torch.float64)
        self.hyperparameters_ = {"arch": "3-32-32-2 tanh", "epochs": EPOCHS}
        _train(self.net_, X, y)


class _FourierEnc(nn.Module):
    """Random Fourier features: smooth low-dimensional fields are easier to fit
    in a lifted sinusoidal basis than in raw coordinates."""

    def __init__(self, n_feat, scale, gen):
        super().__init__()
        B = torch.randn(3, n_feat, generator=gen, dtype=torch.float64) * scale
        self.register_buffer("B", B)

    def forward(self, x):
        p = 2.0 * np.pi * x @ self.B
        return torch.cat([torch.sin(p), torch.cos(p)], dim=-1)


class FourierMLP(_Torch):
    family = "fourier_mlp"

    def _fit_normalized(self, X, y):
        torch.manual_seed(self.seed)
        g = torch.Generator().manual_seed(self.seed)
        nf, scale = 32, 0.6
        self.net_ = nn.Sequential(_FourierEnc(nf, scale, g),
                                  nn.Linear(2 * nf, 64), nn.Tanh(),
                                  nn.Linear(64, 64), nn.Tanh(),
                                  nn.Linear(64, 2)).to(dtype=torch.float64)
        self.hyperparameters_ = {"arch": "RFF32 -> 64-64-2 tanh",
                                 "rff_scale": scale, "epochs": EPOCHS}
        _train(self.net_, X, y)


class Sine(nn.Module):
    def __init__(self, w0=6.0):
        super().__init__(); self.w0 = w0

    def forward(self, x):
        return torch.sin(self.w0 * x)


class Siren(_Torch):
    """Sinusoidal-activation net; strong on smooth continuous fields."""
    family = "siren"

    def _fit_normalized(self, X, y):
        torch.manual_seed(self.seed)
        self.net_ = nn.Sequential(nn.Linear(3, 64), Sine(6.0),
                                  nn.Linear(64, 64), Sine(1.0),
                                  nn.Linear(64, 2)).to(dtype=torch.float64)
        self.hyperparameters_ = {"arch": "3-64-64-2 sine(w0=6)", "epochs": EPOCHS}
        _train(self.net_, X, y)


class _ResBlock(nn.Module):
    def __init__(self, w):
        super().__init__()
        self.f = nn.Sequential(nn.Linear(w, w), nn.Tanh(), nn.Linear(w, w))
        self.a = nn.Tanh()

    def forward(self, x):
        return self.a(x + self.f(x))


class ResMLP(_Torch):
    family = "residual_mlp"

    def _fit_normalized(self, X, y):
        torch.manual_seed(self.seed)
        w = 48
        self.net_ = nn.Sequential(nn.Linear(3, w), nn.Tanh(),
                                  _ResBlock(w), _ResBlock(w),
                                  nn.Linear(w, 2)).to(dtype=torch.float64)
        self.hyperparameters_ = {"arch": f"3-{w} + 2 resblocks -> 2", "epochs": EPOCHS}
        _train(self.net_, X, y)


class DeepEnsemble(_Torch):
    """Five independently initialised compact MLPs, averaged."""
    family = "deep_ensemble"

    def _fit_normalized(self, X, y):
        self.members_ = []
        for k in range(5):
            torch.manual_seed(self.seed + 7919 * k)
            net = nn.Sequential(nn.Linear(3, 32), nn.Tanh(),
                                nn.Linear(32, 32), nn.Tanh(),
                                nn.Linear(32, 2)).to(dtype=torch.float64)
            self.members_.append(_train(net, X, y))
        self.hyperparameters_ = {"arch": "5x 3-32-32-2 tanh, mean", "epochs": EPOCHS}

    def _predict_normalized(self, X):
        Xt = torch.as_tensor(X, dtype=torch.float64)
        with torch.no_grad():
            return np.mean([m(Xt).cpu().numpy() for m in self.members_], axis=0)


class ReciprocityMLP(_Torch):
    """Plain MLP with a SOFT reciprocity penalty.

    The energy net enforces d(lambda_d)/d(iq) = d(lambda_q)/d(id) structurally.
    This asks whether penalising the same identity gets the same benefit without
    the constrained architecture.
    """
    family = "reciprocity_penalised_mlp"

    def _fit_normalized(self, X, y):
        torch.manual_seed(self.seed)
        self.net_ = nn.Sequential(nn.Linear(3, 32), nn.Tanh(),
                                  nn.Linear(32, 32), nn.Tanh(),
                                  nn.Linear(32, 2)).to(dtype=torch.float64)
        w = 1.0
        xs = torch.as_tensor(self.x_scale_, dtype=torch.float64)
        ys = torch.as_tensor(self.y_scale_, dtype=torch.float64)

        def pen(net, Xt):
            xin = Xt.clone().requires_grad_(True)
            out = net(xin)
            gd = torch.autograd.grad(out[:, 0].sum(), xin, create_graph=True)[0]
            gq = torch.autograd.grad(out[:, 1].sum(), xin, create_graph=True)[0]
            # chain rule back to physical currents
            dld_diq = gd[:, 1] * ys[0] / xs[1]
            dlq_did = gq[:, 0] * ys[1] / xs[0]
            return w * ((dld_diq - dlq_did) ** 2).mean()

        self.hyperparameters_ = {"arch": "3-32-32-2 tanh + reciprocity penalty",
                                 "penalty_weight": w, "epochs": EPOCHS}
        _train(self.net_, X, y, extra_loss=pen)


# ----------------------------------------------------------------- harness
manifest = json.loads(open("eesm/configs/eesm_experiment_manifest.json").read())
strategies, budgets, families, seeds = _validate_manifest(manifest)
domain = _domain_from_manifest(manifest)
P = int(manifest["machine"]["pole_pairs"])
table = {r["point_id"]: r for r in
         csv.DictReader(open("out/eesm/femm_equal_budget_20260813/femm_results.csv",
                             newline=""))
         if str(r["converged"]).lower() in ("true", "1")}


def truth(ids):
    o = []
    for pid in ids:
        if pid == ORIGIN_ID and pid not in table:
            o.append([0.0, 0.0]); continue
        r = table[pid]; o.append([float(r["lambda_d_wb"]), float(r["lambda_q_wb"])])
    return np.array(o)


def torque(f, c):
    return 1.5 * P * (f[:, 0] * c[:, 1] - f[:, 1] * c[:, 0])


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


rb = max(budgets)
sel = latin_hypercube_samples(domain, n=rb,
                              seed=_derived_seed(seeds["split"], "selection", rb))
selX, selY = _sample_matrix(sel), truth([str(v) for v in sel["point_id"]])
selT = torque(selY, selX)

ARCHS = [("mlp_300 (Phase 0)", None), ("mlp_600", MLP600),
         ("fourier_mlp", FourierMLP), ("siren", Siren),
         ("residual_mlp", ResMLP), ("deep_ensemble", DeepEnsemble),
         ("reciprocity_mlp", ReciprocityMLP)]

out = {}
print(f"{'cell':<20}" + "".join(f"{n.split()[0][:13]:>14}" for n, _ in ARCHS))
for strategy in strategies:
    for b in budgets:
        ss = _derived_seed(seeds["split"], strategy, b)
        d = _sample_training(strategy, domain, b, ss)
        X, Y = _sample_matrix(d), truth([str(v) for v in d["point_id"]])
        cell = {}
        for name, cls in ARCHS:
            vals = []
            for k in range(SEEDS_PER):
                s = 1701 + 104729 * k
                m = (build_surrogate("compact_mlp", seed=s, config={}) if cls is None
                     else cls(seed=s, config={}))
                m.fit(X, Y)
                vals.append(rmse(torque(m.predict(selX), selX), selT))
            cell[name] = {"median": float(np.median(vals)),
                          "all": [float(v) for v in vals]}
        out[f"{strategy}|{b}"] = cell
        print(f"{strategy+'|'+str(b):<20}" +
              "".join(f"{cell[n]['median']:>14.4f}" for n, _ in ARCHS))

print("\nmedian-of-cells by architecture (lower is better):")
for name, _ in ARCHS:
    v = [out[c][name]["median"] for c in out]
    print(f"  {name:<22} median {np.median(v):.4f}   best cell {min(v):.4f}")

json.dump({"epochs": EPOCHS, "seeds_per_arch": SEEDS_PER, "cells": out},
          open("/home/claude/ann_sweep.json", "w"), indent=1)
print("\nwrote /home/claude/ann_sweep.json")
