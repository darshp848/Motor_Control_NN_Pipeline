"""Train + compare multiple surrogate architectures on the IPM flux map.

Reads:
    data/flux_map_fem.csv         (header: Id,Iq,Phi_d,Phi_q)

Trains a suite of models and compares them on a held-out test set:
  closed_form:
    1. linear              - least squares (no interactions)
    2. poly_deg2           - polynomial degree 2 (Id, Iq, Id*Iq, Id^2, Iq^2)
    3. poly_deg3           - polynomial degree 3 (adds cubic terms)
    4. poly_deg4           - polynomial degree 4
    5. rbf_linear          - fixed RBF feature map + ridge (closed form)
  sklearn:
    6. gaussian_process    - GP with RBF + WhiteKernel (multi-output)
    7. random_forest       - RandomForestRegressor (multi-output)
    8. gradient_boosting   - HistGradientBoostingRegressor per output
  torch (MLPs, single network predicts both Phi_d and Phi_q):
    9. mlp_small           - 2 -> 32  -> 32  -> 2, ReLU
   10. mlp_medium          - 2 -> 64  -> 64  -> 2, ReLU + dropout(0.1)
   11. mlp_large           - 2 -> 128 -> 128 -> 64 -> 2, ReLU + dropout(0.2)
   12. mlp_phys_features   - 2 -> 64  -> 64  -> 2 with augmented input
                                                (Id, Iq, Id*Iq, Id^2, Iq^2)

For every model the script reports train / val / test RMSE + R^2 on BOTH
Phi_d and Phi_q, saves a per-model artifact in out/models/, writes a dense
prediction grid CSV per model in out/predictions/, and produces two plots
in out/plots/: a side-by-side Phi_d comparison and a per-model validation
scatter.

After all models are trained the script picks the winner by lowest mean
test RMSE across (Phi_d, Phi_q) and writes a self-contained
inference_flux_map.py next to this script that loads the winning artifact
and exposes:

    from inference_flux_map import predict
    phi_d, phi_q = predict(Id=12.3, Iq=-4.5)

Designed to NOT touch AEDT or the running sweep. Pure Python, just IO of
the CSV produced by gui_full_magnetostatic_export.py.

Usage (from repo root):

    .venv\\Scripts\\python train_flux_map_comparison.py \\
        --csv data/flux_map_fem.csv \\
        --out out

If --csv is omitted, the script tries the default path. If the CSV does
not exist yet (FEM run not finished) it exits cleanly with a message
instead of crashing. Re-run the same command once the CSV is there.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np

warnings.filterwarnings("ignore")  # sklearn/torch convergence notices


# ---------------------------------------------------------------------------
# Optional imports. Each model checks its availability and skips gracefully.
# ---------------------------------------------------------------------------

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

try:
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
    from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler as SkScaler
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_squared_error, r2_score
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

try:
    import torch
    from torch import nn
    torch.manual_seed(0)
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False


# ---------------------------------------------------------------------------
# IO + preprocessing.
# ---------------------------------------------------------------------------

DEFAULT_CSV = os.path.join("data", "flux_map_fem.csv")


def load_dataset(csv_path: str):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            "Flux map CSV not found at: " + csv_path + "\n"
            "Either the FEM sweep is still running or the path is wrong. "
            "Re-run this script after the sweep produces the CSV."
        )
    if _HAS_PANDAS:
        df = pd.read_csv(csv_path)
        cols = list(df.columns)
        if cols[:4] != ["Id", "Iq", "Phi_d", "Phi_q"]:
            raise RuntimeError("Expected header Id,Iq,Phi_d,Phi_q, got " + str(cols))
        X = df[["Id", "Iq"]].to_numpy(np.float64)
        Y = df[["Phi_d", "Phi_q"]].to_numpy(np.float64)
    else:
        # Pure-numpy fallback reader.
        with open(csv_path, "r") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        header = lines[0].split(",")
        if header[:4] != ["Id", "Iq", "Phi_d", "Phi_q"]:
            raise RuntimeError("Expected header Id,Iq,Phi_d,Phi_q, got " + str(header))
        rows = np.array([[float(v) for v in ln.split(",")[:4]] for ln in lines[1:]],
                        dtype=np.float64)
        X, Y = rows[:, :2], rows[:, 2:4]
    return X, Y


def standardize(X):
    mu = X.mean(axis=0)
    sigma = X.std(axis=0) + 1e-12
    return (X - mu) / sigma, mu, sigma


def train_val_test_split(X, Y, seed=0, val_frac=0.15, test_frac=0.15):
    rng = np.random.default_rng(seed)
    n = X.shape[0]
    idx = rng.permutation(n)
    n_val = int(n * val_frac)
    n_test = int(n * test_frac)
    n_train = n - n_val - n_test
    tr = idx[:n_train]
    va = idx[n_train:n_train + n_val]
    te = idx[n_train + n_val:]
    return (
        (X[tr], Y[tr]),
        (X[va], Y[va]),
        (X[te], Y[te]),
        tr, va, te,
    )


# ---------------------------------------------------------------------------
# Metrics.
# ---------------------------------------------------------------------------

def metrics(y_true, y_pred):
    """Per-output RMSE + R^2 averaged across outputs."""
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2, axis=0))  # shape (2,)
    ss_res = np.sum((y_true - y_pred) ** 2, axis=0)
    ss_tot = np.sum((y_true - y_true.mean(axis=0)) ** 2, axis=0) + 1e-12
    r2 = 1.0 - ss_res / ss_tot
    return {
        "rmse_phi_d": float(rmse[0]),
        "rmse_phi_q": float(rmse[1]),
        "rmse_mean": float(rmse.mean()),
        "r2_phi_d": float(r2[0]),
        "r2_phi_q": float(r2[1]),
        "r2_mean": float(r2.mean()),
    }


# ---------------------------------------------------------------------------
# Model registry. Each model is a class with .fit(Xtr, Ytr) and .predict(X).
# We DO NOT cross-contaminate preprocessing: every model StandardScaler-fits
# only on the training split and applies it consistently to val/test.
# ---------------------------------------------------------------------------

@dataclass
class BaseModel:
    name: str = "base"
    fit_seconds: float = 0.0
    artifact_path: str | None = None  # set by save_artifact()

    def fit(self, Xtr, Ytr):  # pragma: no cover - subclassed
        raise NotImplementedError

    def predict(self, X):  # pragma: no cover - subclassed
        raise NotImplementedError

    def save_artifact(self, out_dir):
        return None


# ---- closed-form linear / polynomial -----------------------------------

class PolyModel(BaseModel):
    def __init__(self, degree: int, name: str):
        self.degree = degree
        self.name = name
        self.coeffs = None
        self.x_mu = None
        self.x_sigma = None
        self.power_index = None

    def _design(self, X):
        n = X.shape[0]
        feats = [np.ones((n, 1))]
        ids = []
        for d in range(1, self.degree + 1):
            for ix in (0, 1):
                feats.append((X[:, ix:ix + 1] ** d))
                ids.append((d, ix))
            if d >= 2:
                feats.append((X[:, 0:1] ** (d - 1)) * (X[:, 1:2]))
                feats.append((X[:, 0:1]) * (X[:, 1:2] ** (d - 1)))
                ids.append((d - 1, 0, 1, d - 1, 1, 0))
                ids.append((d - 1, 1, 0, 1, 0, d - 1))
        return np.hstack(feats)

    def fit(self, Xtr, Ytr):
        # Standardize inputs (helps conditioning for high-degree polys)
        self.x_mu = Xtr.mean(axis=0)
        self.x_sigma = Xtr.std(axis=0) + 1e-12
        Xs = (Xtr - self.x_mu) / self.x_sigma
        Phi = self._design(Xs)
        # Ridge closed form: (Phi^T Phi + lambda I) w = Phi^T Y
        lam = 1e-3
        A = Phi.T @ Phi + lam * np.eye(Phi.shape[1])
        b = Phi.T @ Ytr
        self.coeffs = np.linalg.solve(A, b)
        return self

    def predict(self, X):
        Xs = (X - self.x_mu) / self.x_sigma
        Phi = self._design(Xs)
        return Phi @ self.coeffs

    def save_artifact(self, out_dir):
        path = os.path.join(out_dir, self.name + ".npz")
        np.savez(path, coeffs=self.coeffs, x_mu=self.x_mu, x_sigma=self.x_sigma,
                 degree=self.degree)
        self.artifact_path = path
        return path

    @classmethod
    def load(cls, path):
        z = np.load(path)
        m = cls(int(z["degree"]), os.path.basename(path).rsplit(".", 1)[0])
        m.coeffs = z["coeffs"]
        m.x_mu = z["x_mu"]
        m.x_sigma = z["x_sigma"]
        return m


class RBFModel(BaseModel):
    """Fixed RBF feature map + ridge regression. Closed form, no scipy
    needed beyond numpy. Centers are chosen as a uniform subset of the
    training inputs."""

    def __init__(self, n_centers: int = 60, gamma: float = 0.5, name: str = "rbf_linear"):
        self.n_centers = n_centers
        self.gamma = gamma
        self.name = name
        self.centers = None
        self.coeffs = None
        self.x_mu = None
        self.x_sigma = None

    @staticmethod
    def _rbf(X, C, gamma):
        # X: (n,2), C: (k,2).  Returns (n,k).
        d2 = (
            (X ** 2).sum(axis=1, keepdims=True)
            + (C ** 2).sum(axis=1)
            - 2.0 * X @ C.T
        )
        return np.exp(-gamma * np.maximum(d2, 0.0))

    def fit(self, Xtr, Ytr):
        self.x_mu = Xtr.mean(axis=0)
        self.x_sigma = Xtr.std(axis=0) + 1e-12
        Xs = (Xtr - self.x_mu) / self.x_sigma
        # Pick ~n_centers spread out via farthest-point sampling (truncated
        # to keep it cheap). Falls back to uniform stride if too few rows.
        n = Xs.shape[0]
        if n <= self.n_centers:
            self.centers = Xs.copy()
        else:
            rng = np.random.default_rng(0)
            idx = [int(rng.integers(0, n))]
            d2 = ((Xs - Xs[idx[0]]) ** 2).sum(axis=1)
            for _ in range(self.n_centers - 1):
                j = int(np.argmax(d2))
                idx.append(j)
                d2 = np.minimum(d2, ((Xs - Xs[j]) ** 2).sum(axis=1))
            self.centers = Xs[idx]
        Phi = self._rbf(Xs, self.centers, self.gamma)
        Phi = np.hstack([np.ones((Phi.shape[0], 1)), Phi])
        lam = 1e-3
        A = Phi.T @ Phi + lam * np.eye(Phi.shape[1])
        self.coeffs = np.linalg.solve(A, Phi.T @ Ytr)
        return self

    def predict(self, X):
        Xs = (X - self.x_mu) / self.x_sigma
        Phi = self._rbf(Xs, self.centers, self.gamma)
        Phi = np.hstack([np.ones((Phi.shape[0], 1)), Phi])
        return Phi @ self.coeffs

    def save_artifact(self, out_dir):
        path = os.path.join(out_dir, self.name + ".npz")
        np.savez(path, centers=self.centers, coeffs=self.coeffs,
                 x_mu=self.x_mu, x_sigma=self.x_sigma,
                 gamma=self.gamma, n_centers=self.n_centers)
        self.artifact_path = path
        return path


# ---- sklearn models ----------------------------------------------------

if _HAS_SKLEARN:

    class GPModel(BaseModel):
        def __init__(self, name: str = "gaussian_process"):
            self.name = name
            self.model = None
            self.scaler = None

        def fit(self, Xtr, Ytr):
            self.scaler = SkScaler()
            Xs = self.scaler.fit_transform(Xtr)
            kernel = ConstantKernel(1.0, (1e-2, 1e2)) * RBF(
                length_scale=[1.0, 1.0], length_scale_bounds=(1e-2, 1e2)
            ) + WhiteKernel(noise_level=1e-4, noise_level_bounds=(1e-8, 1e0))
            self.model = GaussianProcessRegressor(
                kernel=kernel, n_restarts_optimizer=4, normalize_y=True,
                random_state=0,
            )
            self.model.fit(Xs, Ytr)
            return self

        def predict(self, X):
            Xs = self.scaler.transform(X)
            return self.model.predict(Xs)

        def save_artifact(self, out_dir):
            import pickle
            path = os.path.join(out_dir, self.name + ".pkl")
            with open(path, "wb") as f:
                pickle.dump({"model": self.model, "scaler": self.scaler,
                             "name": self.name}, f)
            self.artifact_path = path
            return path

    class RFModel(BaseModel):
        def __init__(self, name: str = "random_forest"):
            self.name = name
            self.model = None

        def fit(self, Xtr, Ytr):
            self.model = RandomForestRegressor(
                n_estimators=400, max_depth=None, min_samples_leaf=2,
                n_jobs=-1, random_state=0,
            )
            self.model.fit(Xtr, Ytr)
            return self

        def predict(self, X):
            return self.model.predict(X)

        def save_artifact(self, out_dir):
            import pickle
            path = os.path.join(out_dir, self.name + ".pkl")
            with open(path, "wb") as f:
                pickle.dump({"model": self.model, "name": self.name}, f)
            self.artifact_path = path
            return path

    class GBRModel(BaseModel):
        """Per-output HistGradientBoostingRegressor wrapped in
        MultiOutputRegressor since HGBR is single-output."""

        def __init__(self, name: str = "gradient_boosting"):
            self.name = name
            self.model = None

        def fit(self, Xtr, Ytr):
            base = HistGradientBoostingRegressor(
                max_iter=400, learning_rate=0.05, max_depth=4,
                min_samples_leaf=10, l2_regularization=1e-3, random_state=0,
            )
            self.model = MultiOutputRegressor(base, n_jobs=-1)
            self.model.fit(Xtr, Ytr)
            return self

        def predict(self, X):
            return self.model.predict(X)

        def save_artifact(self, out_dir):
            import pickle
            path = os.path.join(out_dir, self.name + ".pkl")
            with open(path, "wb") as f:
                pickle.dump({"model": self.model, "name": self.name}, f)
            self.artifact_path = path
            return path


# ---- torch MLPs -------------------------------------------------------

if _HAS_TORCH:

    def _train_torch_model(net, Xtr, Ytr, Xva, Yva, epochs=2000, lr=2e-3,
                           batch_size=128, patience=80, device="cpu"):
        opt = torch.optim.Adam(net.parameters(), lr=lr)
        loss_fn = nn.MSELoss()

        Xt = torch.from_numpy(Xtr).float().to(device)
        Yt = torch.from_numpy(Ytr).float().to(device)
        Xv = torch.from_numpy(Xva).float().to(device)
        Yv = torch.from_numpy(Yva).float().to(device)

        n = Xt.shape[0]
        best_val = float("inf")
        best_state = None
        bad = 0
        rng = torch.Generator().manual_seed(0)

        for ep in range(epochs):
            net.train()
            perm = torch.randperm(n, generator=rng)
            for i in range(0, n, batch_size):
                b = perm[i:i + batch_size]
                opt.zero_grad()
                pred = net(Xt[b])
                loss = loss_fn(pred, Yt[b])
                loss.backward()
                opt.step()
            net.eval()
            with torch.no_grad():
                val_loss = float(loss_fn(net(Xv), Yv))
            if val_loss + 1e-12 < best_val:
                best_val = val_loss
                best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
                bad = 0
            else:
                bad += 1
                if bad >= patience:
                    break
        if best_state is not None:
            net.load_state_dict(best_state)
        return net, best_val


    class _MLPSmall(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(2, 32), nn.ReLU(),
                nn.Linear(32, 32), nn.ReLU(),
                nn.Linear(32, 2),
            )
        def forward(self, x): return self.net(x)


    class _MLPMedium(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(2, 64), nn.ReLU(), nn.Dropout(0.1),
                nn.Linear(64, 64), nn.ReLU(), nn.Dropout(0.1),
                nn.Linear(64, 2),
            )
        def forward(self, x): return self.net(x)


    class _MLPLarge(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(2, 128), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(128, 128), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.1),
                nn.Linear(64, 2),
            )
        def forward(self, x): return self.net(x)


    class _MLPPhys(nn.Module):
        """Input augmented with Id*Iq, Id^2, Iq^2 (in raw space)."""
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(5, 64), nn.ReLU(), nn.Dropout(0.1),
                nn.Linear(64, 64), nn.ReLU(), nn.Dropout(0.1),
                nn.Linear(64, 2),
            )
        def forward(self, x):
            aug = torch.cat([
                x,
                (x[:, 0:1] * x[:, 1:2]),
                (x[:, 0:1] ** 2),
                (x[:, 1:2] ** 2),
            ], dim=1)
            return self.net(aug)


    class _MLPPhysAdapter(nn.Module):
        """Wraps _MLPPhys so the public interface takes (n,2) raw current
        inputs and the standardization happens inside."""
        def __init__(self, x_mu, x_sigma):
            super().__init__()
            self.x_mu = nn.Parameter(torch.tensor(x_mu).float(), requires_grad=False)
            self.x_sigma = nn.Parameter(torch.tensor(x_sigma).float(), requires_grad=False)
            self.net = _MLPPhys()
        def forward(self, x):
            xs = (x - self.x_mu) / self.x_sigma
            aug = torch.cat([
                xs,
                (xs[:, 0:1] * xs[:, 1:2]),
                (xs[:, 0:1] ** 2),
                (xs[:, 1:2] ** 2),
            ], dim=1)
            return self.net.net(aug)


    class TorchModel(BaseModel):
        def __init__(self, net: nn.Module, name: str, epochs=2000):
            self.net = net
            self.name = name
            self.epochs = epochs
            self.x_mu = None
            self.x_sigma = None
            self.y_mu = None
            self.y_sigma = None
            self.device = "cpu"

        def fit(self, Xtr, Ytr):
            self.x_mu = Xtr.mean(axis=0)
            self.x_sigma = Xtr.std(axis=0) + 1e-12
            self.y_mu = Ytr.mean(axis=0)
            self.y_sigma = Ytr.std(axis=0) + 1e-12
            Xs = (Xtr - self.x_mu) / self.x_sigma
            Ys = (Ytr - self.y_mu) / self.y_sigma
            # Dummy val split for early stopping - uses 10% of training.
            rng = np.random.default_rng(0)
            n = Xs.shape[0]
            idx = rng.permutation(n)
            n_val = max(8, n // 10)
            va_idx = idx[:n_val]
            tr_idx = idx[n_val:]
            self.net.to(self.device)
            self.net, _ = _train_torch_model(
                self.net, Xs[tr_idx], Ys[tr_idx], Xs[va_idx], Ys[va_idx],
                epochs=self.epochs,
            )
            return self

        def predict(self, X):
            self.net.eval()
            with torch.no_grad():
                Xs = (X - self.x_mu) / self.x_sigma
                Xt = torch.from_numpy(Xs).float().to(self.device)
                Ys = self.net(Xt).cpu().numpy()
            return Ys * self.y_sigma + self.y_mu

        def save_artifact(self, out_dir):
            path = os.path.join(out_dir, self.name + ".pt")
            torch.save({
                "state_dict": self.net.state_dict(),
                "x_mu": self.x_mu, "x_sigma": self.x_sigma,
                "y_mu": self.y_mu, "y_sigma": self.y_sigma,
                "name": self.name,
                "arch": self.net.__class__.__name__,
            }, path)
            self.artifact_path = path
            return path


# ---------------------------------------------------------------------------
# Pipeline.
# ---------------------------------------------------------------------------

def build_candidates(Xtr):
    out = []
    out.append(PolyModel(1, "linear"))
    out.append(PolyModel(2, "poly_deg2"))
    out.append(PolyModel(3, "poly_deg3"))
    out.append(PolyModel(4, "poly_deg4"))
    out.append(RBFModel(n_centers=60, gamma=0.5, name="rbf_linear"))
    if _HAS_SKLEARN:
        out.append(GPModel())
        out.append(RFModel())
        out.append(GBRModel())
    if _HAS_TORCH:
        out.append(TorchModel(_MLPSmall(), "mlp_small", epochs=2000))
        out.append(TorchModel(_MLPMedium(), "mlp_medium", epochs=2000))
        out.append(TorchModel(_MLPLarge(), "mlp_large", epochs=2000))
        # Phys-features model: needs an adapter that does standardization
        # internally. We pass dummy mu/sigma here; the real ones are set in
        # TorchModel.fit() and used by predict(); the adapter is just for
        # the augmented forward.
        out.append(TorchModel(_MLPPhysAdapter(np.zeros(2), np.ones(2)),
                              "mlp_phys_features", epochs=2000))
    return out


def predict_grid(model, id_grid, iq_grid):
    """Vectorized prediction over an Id x Iq meshgrid for plotting."""
    II, QQ = np.meshgrid(id_grid, iq_grid)
    X = np.stack([II.ravel(), QQ.ravel()], axis=1)
    try:
        Y = model.predict(X)
    except Exception as exc:
        return None, None, str(exc)
    return Y[:, 0].reshape(II.shape), Y[:, 1].reshape(II.shape), None


def main(args):
    csv_path = args.csv
    out_dir = args.out
    print(f"[load] reading {csv_path}")
    X_all, Y_all = load_dataset(csv_path)
    print(f"[load] {X_all.shape[0]} rows, Id range "
          f"[{X_all[:,0].min():.3f}, {X_all[:,0].max():.3f}], "
          f"Iq range [{X_all[:,1].min():.3f}, {X_all[:,1].max():.3f}]")
    print(f"[load] Phi_d range [{Y_all[:,0].min():.4f}, {Y_all[:,0].max():.4f}] Wb")
    print(f"[load] Phi_q range [{Y_all[:,1].min():.4f}, {Y_all[:,1].max():.4f}] Wb")

    # NOTICE: we standardize ONCE on the training split only; each model
    # handles the scaling internally (closed-form models store it, sklearn
    # models pipeline their own scaler, torch models store it). So we pass
    # RAW inputs to every model. This keeps the public decision boundary:
    # predict(Id, Iq) takes raw currents.
    (Xtr, Ytr), (Xva, Yva), (Xte, Yte), tr_idx, va_idx, te_idx = \
        train_val_test_split(X_all, Y_all, seed=0)

    dirs = {k: os.path.join(out_dir, k)
            for k in ("models", "predictions", "plots", "logs")}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    np.savez(os.path.join(dirs["models"], "split_indices.npz"),
             tr=tr_idx, va=va_idx, te=te_idx)
    np.save(os.path.join(dirs["models"], "X_all.npy"), X_all)
    np.save(os.path.join(dirs["models"], "Y_all.npy"), Y_all)

    candidates = build_candidates(Xtr)
    results = []

    for model in candidates:
        print(f"\n=== {model.name} ===")
        t0 = time.time()
        try:
            model.fit(Xtr, Ytr)
        except Exception as exc:
            print(f"  fit failed: {exc}")
            results.append({"name": model.name, "status": "fit_failed",
                            "error": str(exc)})
            continue
        model.fit_seconds = time.time() - t0
        print(f"  fit done in {model.fit_seconds:.2f}s")

        try:
            ptr = model.predict(Xtr)
            pva = model.predict(Xva)
            pte = model.predict(Xte)
        except Exception as exc:
            print(f"  predict failed: {exc}")
            results.append({"name": model.name, "status": "predict_failed",
                            "error": str(exc)})
            continue

        m_tr = metrics(Ytr, ptr)
        m_va = metrics(Yva, pva)
        m_te = metrics(Yte, pte)
        print(f"  train RMSE: Phi_d={m_tr['rmse_phi_d']:.5f} "
              f"Phi_q={m_tr['rmse_phi_q']:.5f}")
        print(f"  val   RMSE: Phi_d={m_va['rmse_phi_d']:.5f} "
              f"Phi_q={m_va['rmse_phi_q']:.5f}")
        print(f"  test  RMSE: Phi_d={m_te['rmse_phi_d']:.5f} "
              f"Phi_q={m_te['rmse_phi_q']:.5f}")

        # Save artifact.
        try:
            path = model.save_artifact(dirs["models"])
        except Exception as exc:
            print(f"  save_artifact failed: {exc}")
            path = None

        # Dense prediction grid for plotting.
        id_grid = np.linspace(X_all[:,0].min(), X_all[:,0].max(), 80)
        iq_grid = np.linspace(X_all[:,1].min(), X_all[:,1].max(), 80)
        pd_d, pd_q, err = predict_grid(model, id_grid, iq_grid)
        if pd_d is not None:
            II, QQ = np.meshgrid(id_grid, iq_grid)
            df = np.stack([II.ravel(), QQ.ravel(), pd_d.ravel(),
                           pd_q.ravel()], axis=1)
            np.savetxt(os.path.join(dirs["predictions"],
                                    model.name + "_grid.csv"),
                      df, delimiter=",",
                      header="Id,Iq,Phi_d_pred,Phi_q_pred",
                      comments="", fmt="%.6g")

        results.append({
            "name": model.name,
            "status": "ok",
            "fit_seconds": model.fit_seconds,
            "train": m_tr, "val": m_va, "test": m_te,
            "artifact_path": path,
            "predict_grid_error": err,
        })

    # Write summary CSV + JSON.
    import csv as csvmod
    summary_csv = os.path.join(dirs["logs"], "metrics_summary.csv")
    with open(summary_csv, "w", newline="") as f:
        w = csvmod.writer(f)
        w.writerow([
            "name", "fit_seconds",
            "train_rmse_phi_d", "train_rmse_phi_q", "train_r2_mean",
            "val_rmse_phi_d", "val_rmse_phi_q", "val_r2_mean",
            "test_rmse_phi_d", "test_rmse_phi_q", "test_r2_mean",
        ])
        for r in results:
            if r.get("status") != "ok":
                continue
            w.writerow([
                r["name"], round(r["fit_seconds"], 3),
                r["train"]["rmse_phi_d"], r["train"]["rmse_phi_q"], r["train"]["r2_mean"],
                r["val"]["rmse_phi_d"], r["val"]["rmse_phi_q"], r["val"]["r2_mean"],
                r["test"]["rmse_phi_d"], r["test"]["rmse_phi_q"], r["test"]["r2_mean"],
            ])
    with open(os.path.join(dirs["logs"], "metrics_summary.json"), "w") as f:
        json.dump(results, f, indent=2)

    # Pick winner.
    ok = [r for r in results if r.get("status") == "ok"]
    if not ok:
        print("\n[done] no successful models")
        return 1
    ok.sort(key=lambda r: r["test"]["rmse_mean"])
    winner = ok[0]
    print("\n=== Leaderboard (test RMSE mean across Phi_d+Phi_q) ===")
    for r in ok:
        mark = "  <== winner" if r is winner else ""
        print(f"  {r['name']:<22} test_rmse_mean={r['test']['rmse_mean']:.5f} "
              f"r2_mean={r['test']['r2_mean']:.4f}{mark}")

    # Generate inference_flux_map.py next to this script that loads the
    # winning artifact. Independent of which family won.
    write_inference_file(winner, dirs["models"])

    # Plots.
    if _HAS_MPL:
        plot_val_scatter(results, (Xva, Yva), (Xte, Yte),
                         model_lookup={r["name"]: r for r in results},
                         model_dir=dirs["models"],
                         plot_dir=dirs["plots"])
    print(f"\n[done] artifacts under {dirs['models']}")
    print(f"[done] predictions under {dirs['predictions']}")
    print(f"[done] logs under {dirs['logs']}")
    print(f"[done] inference_flux_map.py written next to this script")
    return 0


# ---------------------------------------------------------------------------
# Inference file generator.
# ---------------------------------------------------------------------------

def write_inference_file(winner, models_dir):
    name = winner["name"]
    artifact = winner.get("artifact_path") or ""
    art_basename = os.path.basename(artifact) if artifact else ""
    art_abs = os.path.abspath(artifact) if artifact else ""
    here = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(here, "inference_flux_map.py")

    # Detect family by name/type of artifact.
    if artifact.endswith(".npz") and name.startswith("poly"):
        loader = f"""
import numpy as np
_ARTIFACT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "out", "models", "{art_basename}")
def _load():
    z = np.load(_ARTIFACT)
    return z["coeffs"], z["x_mu"], z["x_sigma"], int(z["degree"])
_COEFFS, _X_MU, _X_SIGMA, _DEGREE = _load()
def _design(X):
    n = X.shape[0]
    feats = [np.ones((n, 1))]
    for d in range(1, _DEGREE + 1):
        for ix in (0, 1):
            feats.append((X[:, ix:ix + 1] ** d))
        if d >= 2:
            feats.append((X[:, 0:1] ** (d - 1)) * (X[:, 1:2]))
            feats.append((X[:, 0:1]) * (X[:, 1:2] ** (d - 1)))
    return np.hstack(feats)
def predict(Id, Iq):
    X = np.array([[Id, Iq]], dtype=np.float64)
    Xs = (X - _X_MU) / _X_SIGMA
    Phi = _design(Xs)
    Y = Phi @ _COEFFS
    return float(Y[0, 0]), float(Y[0, 1])
_ARTIFACT_PATH = _ARTIFACT
"""
    elif artifact.endswith(".npz") and name == "rbf_linear":
        loader = f"""
import numpy as np
_ARTIFACT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "out", "models", "{art_basename}")
def _load():
    z = np.load(_ARTIFACT)
    return (z[" centers".strip() if False else "centers"], z["coeffs"],
            z["x_mu"], z["x_sigma"], float(z["gamma"]))
_CENTERS, _COEFFS, _X_MU, _X_SIGMA, _GAMMA = _load()
def _rbf(X, C, g):
    d2 = (X**2).sum(1, keepdims=True) + (C**2).sum(1) - 2.0 * X @ C.T
    return np.exp(-g * np.maximum(d2, 0.0))
def predict(Id, Iq):
    X = np.array([[Id, Iq]], dtype=np.float64)
    Xs = (X - _X_MU) / _X_SIGMA
    Phi = np.hstack([np.ones((1, 1)), _rbf(Xs, _CENTERS, _GAMMA)])
    Y = Phi @ _COEFFS
    return float(Y[0, 0]), float(Y[0, 1])
_ARTIFACT_PATH = _ARTIFACT
"""
    elif artifact.endswith(".pkl"):
        loader = f"""
import pickle, os
import numpy as np
_ARTIFACT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "out", "models", "{art_basename}")
with open(_ARTIFACT, "rb") as _f:
    _obj = pickle.load(_f)
_MODEL = _obj["model"]
_SCALER = _obj.get("scaler")
def predict_batch(X):
    X = np.asarray(X, dtype=np.float64)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    Xs = _SCALER.transform(X) if _SCALER is not None else X
    Y = np.asarray(_MODEL.predict(Xs), dtype=np.float64)
    if Y.ndim == 1:
        Y = Y.reshape(-1, 2)
    return Y
def predict(Id, Iq):
    Y = predict_batch([[Id, Iq]])
    return float(Y[0, 0]), float(Y[0, 1])
_ARTIFACT_PATH = _ARTIFACT
"""
    elif artifact.endswith(".pt"):
        # Need to import torch and rebuild the right arch.
        arch_map = {
            "mlp_small": "_MLPSmall",
            "mlp_medium": "_MLPMedium",
            "mlp_large": "_MLPLarge",
            "mlp_phys_features": "_MLPPhysAdapter",
        }
        arch_cls = arch_map.get(name, "_MLPMedium")
        loader = f"""
import os, numpy as np
try:
    import torch
    from torch import nn
except ImportError as _e:
    raise ImportError("inference_flux_map.py needs torch for model '{name}'") from _e

_ARTIFACT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "out", "models", "{art_basename}")
_chk = torch.load(_ARTIFACT, map_location="cpu", weights_only=False)
_ARCH = _chk["arch"]
_X_MU = _chk["x_mu"]; _X_SIGMA = _chk["x_sigma"]
_Y_MU = _chk["y_mu"]; _Y_SIGMA = _chk["y_sigma"]

class _MLPSmall(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(2, 32), nn.ReLU(),
                                 nn.Linear(32, 32), nn.ReLU(),
                                 nn.Linear(32, 2))
    def forward(self, x): return self.net(x)

class _MLPMedium(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(2, 64), nn.ReLU(), nn.Dropout(0.1),
                                 nn.Linear(64, 64), nn.ReLU(), nn.Dropout(0.1),
                                 nn.Linear(64, 2))
    def forward(self, x): return self.net(x)

class _MLPLarge(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(2, 128), nn.ReLU(), nn.Dropout(0.2),
                                 nn.Linear(128, 128), nn.ReLU(), nn.Dropout(0.2),
                                 nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.1),
                                 nn.Linear(64, 2))
    def forward(self, x): return self.net(x)

class _MLPPhys(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(5, 64), nn.ReLU(), nn.Dropout(0.1),
                                 nn.Linear(64, 64), nn.ReLU(), nn.Dropout(0.1),
                                 nn.Linear(64, 2))
    def forward(self, x): return self.net(x)

class _MLPPhysAdapter(nn.Module):
    def __init__(self, x_mu, x_sigma):
        super().__init__()
        self.x_mu = nn.Parameter(torch.tensor(x_mu).float(), requires_grad=False)
        self.x_sigma = nn.Parameter(torch.tensor(x_sigma).float(), requires_grad=False)
        self.net = _MLPPhys()
    def forward(self, x):
        xs = (x - self.x_mu) / self.x_sigma
        aug = torch.cat([xs, (xs[:,0:1] * xs[:,1:2]),
                         (xs[:,0:1]**2), (xs[:,1:2]**2)], dim=1)
        return self.net.net(aug)

_NET_CLS = {{'_MLPSmall': _MLPSmall, '_MLPMedium': _MLPMedium,
            '_MLPLarge': _MLPLarge,
            '_MLPPhysAdapter': _MLPPhysAdapter}}.get(_ARCH, _MLPMedium)
_NET = _NET_CLS()
if _ARCH == '_MLPPhysAdapter':
    _NET = _MLPPhysAdapter(np.zeros(2), np.ones(2))
_NET.load_state_dict(_chk["state_dict"])
_NET.eval()

def predict(Id, Iq):
    X = np.array([[Id, Iq]], dtype=np.float64)
    Xs = (X - _X_MU) / _X_SIGMA
    with torch.no_grad():
        Ys = _NET(torch.from_numpy(Xs).float()).numpy()
    Y = Ys * _Y_SIGMA + _Y_MU
    return float(Y[0, 0]), float(Y[0, 1])
_ARTIFACT_PATH = _ARTIFACT
"""
    else:
        loader = f"""
def predict(Id, Iq):
    raise NotImplementedError("No loader known for winning model '{{}}' "
                              "(artifact: {art_basename})").format("{name}")
"""

    content = (
        '"""Auto-generated by train_flux_map_comparison.py.\n'
        'Loads the best-performing model from out/models/ and exposes\n'
        'predict(Id, Iq) -> (Phi_d, Phi_q) for downstream motor-control code.\n'
        'Regenerate this file by re-running the training script.\n"""\n'
        "import os\n" + loader
    )
    with open(target, "w") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Plots.
# ---------------------------------------------------------------------------

def plot_val_scatter(results, val_pack, test_pack, model_lookup, model_dir,
                     plot_dir, max_models=12):
    if not _HAS_MPL:
        return
    Xva, Yva = val_pack
    Xte, Yte = test_pack
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    ax_d, ax_q = axes
    plotted = 0
    markers = ["o", "s", "^", "v", "D", "P", "*", "X", "<", ">", "h", "p"]
    for r in results:
        if r.get("status") != "ok":
            continue
        m_name = r["name"]
        # Reload model & predict on test for plotting.
        try:
            model = _reload_model_for_plot(r, model_dir)
        except Exception:
            continue
        if model is None:
            continue
        try:
            pred = model.predict(Xte)
        except Exception:
            continue
        ax_d[0].scatter(Yte[:, 0], pred[:, 0], s=18, marker=markers[plotted % 12],
                        alpha=0.7, label=f"{m_name} (RMSE={r['test']['rmse_phi_d']:.4e})")
        ax_q[0].scatter(Yte[:, 1], pred[:, 1], s=18, marker=markers[plotted % 12],
                        alpha=0.7, label=f"{m_name} (RMSE={r['test']['rmse_phi_q']:.4e})")
        ax_d[1].scatter(Xte[:, 0], pred[:, 0] - Yte[:, 0], s=14,
                        marker=markers[plotted % 12], alpha=0.7, label=m_name)
        ax_q[1].scatter(Xte[:, 0], pred[:, 1] - Yte[:, 1], s=14,
                        marker=markers[plotted % 12], alpha=0.7, label=m_name)
        plotted += 1
        if plotted >= max_models:
            break
    lo, hi = Yte[:, 0].min(), Yte[:, 0].max()
    ax_d[0].plot([lo, hi], [lo, hi], "k--", lw=0.6)
    ax_d[0].set_xlabel("Phi_d FEM (Wb)"); ax_d[0].set_ylabel("Phi_d pred (Wb)")
    ax_d[0].set_title("Phi_d test set: predicted vs. true"); ax_d[0].legend(fontsize=7)
    ax_d[1].set_xlabel("Id (A)"); ax_d[1].set_ylabel("Phi_d residual (Wb)")
    ax_d[1].set_title("Phi_d residual vs. Id"); ax_d[1].legend(fontsize=7)
    lo, hi = Yte[:, 1].min(), Yte[:, 1].max()
    ax_q[0].plot([lo, hi], [lo, hi], "k--", lw=0.6)
    ax_q[0].set_xlabel("Phi_q FEM (Wb)"); ax_q[0].set_ylabel("Phi_q pred (Wb)")
    ax_q[0].set_title("Phi_q test set: predicted vs. true"); ax_q[0].legend(fontsize=7)
    ax_q[1].set_xlabel("Id (A)"); ax_q[1].set_ylabel("Phi_q residual (Wb)")
    ax_q[1].set_title("Phi_q residual vs. Id"); ax_q[1].legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(os.path.join(plot_dir, "test_scatter_comparison.png"), dpi=130)
    plt.close(fig)


def _reload_model_for_plot(r, model_dir):
    name = r["name"]
    artifact = r.get("artifact_path")
    if not artifact:
        return None
    if name.startswith("poly_") or name == "linear":
        return PolyModel.load(artifact)
    if name == "rbf_linear":
        z = np.load(artifact)
        m = RBFModel(int(z["n_centers"]), float(z["gamma"]), name)
        m.centers = z["centers"]; m.coeffs = z["coeffs"]
        m.x_mu = z["x_mu"]; m.x_sigma = z["x_sigma"]
        return m
    if artifact.endswith(".pkl"):
        import pickle
        with open(artifact, "rb") as f:
            obj = pickle.load(f)
        class _Wrap:
            def __init__(s, m, scaler=None):
                s.m = m; s.scaler = scaler
            def predict(s, X):
                if s.scaler is not None:
                    X2 = s.scaler.transform(X)
                else:
                    X2 = X
                return np.asarray(s.m.predict(X2)).reshape(-1, 2)
        return _Wrap(obj["model"], obj.get("scaler"))
    if artifact.endswith(".pt") and _HAS_TORCH:
        chk = torch.load(artifact, map_location="cpu", weights_only=False)
        arch = chk["arch"]
        arch_map = {
            "_MLPSmall": _MLPSmall, "_MLPMedium": _MLPMedium,
            "_MLPLarge": _MLPLarge, "_MLPPhysAdapter": _MLPPhysAdapter,
        }
        cls = arch_map.get(arch, _MLPMedium)
        if arch == "_MLPPhysAdapter":
            net = _MLPPhysAdapter(np.zeros(2), np.ones(2))
        else:
            net = cls()
        net.load_state_dict(chk["state_dict"]); net.eval()
        class _Wrap:
            def __init__(s, net, xm, xs, ym, ys):
                s.net = net; s.xm = xm; s.xs = xs; s.ym = ym; s.ys = ys
            def predict(s, X):
                Xs = (X - s.xm) / s.xs
                with torch.no_grad():
                    Ys = s.net(torch.from_numpy(Xs).float()).numpy()
                return Ys * s.ys + s.ym
        return _Wrap(net, chk["x_mu"], chk["x_sigma"], chk["y_mu"], chk["y_sigma"])
    return None


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--csv", default=DEFAULT_CSV,
                   help="Path to flux_map_fem.csv. Default: " + DEFAULT_CSV)
    p.add_argument("--out", default="out",
                   help="Output dir for models/predictions/plots. Default: out")
    p.add_argument("--seed", type=int, default=0)
    ns = p.parse_args()
    try:
        rc = main(ns)
    except FileNotFoundError as e:
        print(str(e))
        sys.exit(2)
    sys.exit(rc or 0)