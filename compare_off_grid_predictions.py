"""OFF-GRID MODEL COMPARISON (run in the venv python, NOT in AEDT).

Reads:
  data/off_grid_fem_results.csv
      (Id, Iq, Phi_d, Phi_q)  - the TRUE FEM flux at 20 off-grid points
  out/logs/metrics_summary.json
      - per-model in-grid train/val/test metrics + artifact paths

For every model that the training script saved, this script:
  1. Reloads the artifact via train_flux_map_comparison._reload_model_for_plot
     (handles npz / pkl / pt uniformly and exposes .predict(X) -> (n,2)).
  2. Predicts (Phi_d, Phi_q) at every off-grid (Id, Iq).
  3. Computes off-grid RMSE + R^2 for Phi_d, Phi_q, mean.
  4. Adds the off-grid numbers to the in-grid ones from metrics_summary.json
     so you can see interpolation vs extrapolation gaps side by side.
  5. Re-ranks the leaderboard by off-grid mean RMSE (the metric that actually
     matters for trusting a surrogate in a controller).
  6. Writes:
       out/validation/off_grid_predictions.csv  - wide table (true + all
                                                   models' predictions)
       out/validation/off_grid_ranking.json     - per-model metrics + rank
       out/validation/off_grid_validation.png   - predicted-vs-true scatter
                                                   + residuals vs. Id

Usage (from repo root, after the AEDT-side validator has run):

    .venv\\Scripts\\python compare_off_grid_predictions.py \\
        --truth data/off_grid_fem_results.csv \\
        --models out --out out

If --truth is omitted, default path used. If the truth CSV is missing, the
script exits cleanly with a message - run validate_off_grid_fem.py in AEDT
first.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")

# Reuse the loaders / model classes defined by the trainer. Both files live at
# the same directory (repo root), so this import works from there.
import train_flux_map_comparison as T


DEFAULT_TRUTH_CSV = os.path.join("data", "off_grid_fem_results.csv")


def load_truth(csv_path):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            "Off-grid FEM truth CSV not found at: " + csv_path + "\n"
            "Run validate_off_grid_fem.py from AEDT first "
            "(Automation -> Run Script)."
        )
    if T._HAS_PANDAS:
        import pandas as pd
        df = pd.read_csv(csv_path)
        cols = list(df.columns)
        if cols[:4] != ["Id", "Iq", "Phi_d", "Phi_q"]:
            raise RuntimeError("Expected header Id,Iq,Phi_d,Phi_q, got " + str(cols))
        X = df[["Id", "Iq"]].to_numpy(np.float64)
        Y = df[["Phi_d", "Phi_q"]].to_numpy(np.float64)
    else:
        with open(csv_path, "r") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        header = lines[0].split(",")
        if header[:4] != ["Id", "Iq", "Phi_d", "Phi_q"]:
            raise RuntimeError("Expected header Id,Iq,Phi_d,Phi_q, got " + str(header))
        rows = np.array([[float(v) for v in ln.split(",")[:4]]
                          for ln in lines[1:]], dtype=np.float64)
        X, Y = rows[:, :2], rows[:, 2:4]
    return X, Y


def per_model_metrics(y_true, y_pred):
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2, axis=0))
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
        "max_abs_err_phi_d": float(np.max(np.abs(y_true[:, 0] - y_pred[:, 0]))),
        "max_abs_err_phi_q": float(np.max(np.abs(y_true[:, 1] - y_pred[:, 1]))),
    }


def main(args):
    truth_csv = args.truth
    models_root = args.models
    out_dir = args.out
    val_dir = os.path.join(out_dir, "validation")
    os.makedirs(val_dir, exist_ok=True)

    print(f"[load] truth CSV: {truth_csv}")
    X, Y = load_truth(truth_csv)
    n_points = X.shape[0]
    print(f"[load] {n_points} off-grid points, "
          f"Id range [{X[:,0].min():.2f}, {X[:,0].max():.2f}], "
          f"Iq range [{X[:,1].min():.2f}, {X[:,1].max():.2f}]")
    print(f"[load] Phi_d range [{Y[:,0].min():.5f}, {Y[:,0].max():.5f}] Wb, "
          f"Phi_q range [{Y[:,1].min():.5f}, {Y[:,1].max():.5f}] Wb")

    summary_path = os.path.join(models_root, "logs", "metrics_summary.json")
    if not os.path.exists(summary_path):
        raise FileNotFoundError(
            "metrics_summary.json not found at: " + summary_path + "\n"
            "Run train_flux_map_comparison.py first."
        )
    with open(summary_path, "r") as f:
        in_grid_results = json.load(f)
    models_dir = os.path.join(models_root, "models")

    # Wide prediction table: Id, Iq, Phi_d_fem, Phi_q_fem, then for each
    # working model: <model>_Phi_d_pred, <model>_Phi_q_pred,
    # <model>_Phi_d_err, <model>_Phi_q_err.
    rows_out = []
    for i in range(n_points):
        rows_out.append({
            "Id": X[i, 0], "Iq": X[i, 1],
            "Phi_d_fem": Y[i, 0], "Phi_q_fem": Y[i, 1],
        })

    leaderboard = []
    n_models = 0
    for r in in_grid_results:
        if r.get("status") != "ok":
            continue
        m_name = r["name"]
        print(f"\n=== {m_name} ===")
        try:
            model = T._reload_model_for_plot(r, models_dir)
        except Exception as exc:
            print(f"  reload failed: {exc}")
            leaderboard.append({
                "name": m_name, "status": "reload_failed", "error": str(exc),
            })
            continue
        if model is None:
            print("  no loader - skipped")
            leaderboard.append({
                "name": m_name, "status": "no_loader",
            })
            continue
        try:
            pred = np.asarray(model.predict(X)).reshape(-1, 2)
        except Exception as exc:
            print(f"  predict failed: {exc}")
            leaderboard.append({
                "name": m_name, "status": "predict_failed", "error": str(exc),
            })
            continue
        m_offgrid = per_model_metrics(Y, pred)
        print(f"  off-grid RMSE: Phi_d={m_offgrid['rmse_phi_d']:.5e} "
              f"Phi_q={m_offgrid['rmse_phi_q']:.5e} "
              f"(max |dPhi_d|={m_offgrid['max_abs_err_phi_d']:.3e}, "
              f"max |dPhi_q|={m_offgrid['max_abs_err_phi_q']:.3e})")
        print(f"  in-grid  test RMSE mean: "
              f"{r['test']['rmse_mean']:.5e}")

        # Fill the wide prediction table.
        for i in range(n_points):
            tag = m_name
            rows_out[i][tag + "_Phi_d_pred"] = float(pred[i, 0])
            rows_out[i][tag + "_Phi_q_pred"] = float(pred[i, 1])
            rows_out[i][tag + "_Phi_d_err"] = float(pred[i, 0] - Y[i, 0])
            rows_out[i][tag + "_Phi_q_err"] = float(pred[i, 1] - Y[i, 1])

        leaderboard.append({
            "name": m_name,
            "status": "ok",
            "in_grid_test": r.get("test", {}),
            "off_grid": m_offgrid,
            "off_grid_rmse_mean": m_offgrid["rmse_mean"],
        })
        n_models += 1

    # Re-rank by off-grid mean RMSE (lower is better).
    ok = [e for e in leaderboard if e.get("status") == "ok"]
    ok.sort(key=lambda e: e["off_grid_rmse_mean"])
    print("\n=== OFF-GRID LEADERBOARD (mean RMSE across Phi_d+Phi_q) ===")
    for i, e in enumerate(ok, 1):
        mark = "  <== off-grid winner" if i == 1 else ""
        print(f"  {i:2d}. {e['name']:<22} "
              f"off_grid_rmse_mean={e['off_grid_rmse_mean']:.5e} "
              f"in_grid_test_rmse_mean={e['in_grid_test']['rmse_mean']:.5e}"
              f"{mark}")

    with open(os.path.join(val_dir, "off_grid_ranking.json"), "w") as f:
        json.dump({
            "n_truth_points": n_points,
            "truth_csv": os.path.abspath(truth_csv),
            "leaderboard": leaderboard,
            "leaderboard_off_grid_sorted": ok,
            "winner_off_grid": ok[0] if ok else None,
        }, f, indent=2)
    print(f"\n[wrote] {os.path.join(val_dir, 'off_grid_ranking.json')}")

    # Wide prediction CSV.
    if T._HAS_PANDAS:
        import pandas as pd
        pd.DataFrame(rows_out).to_csv(
            os.path.join(val_dir, "off_grid_predictions.csv"), index=False
        )
    else:
        # Fallback - write whatever columns every row agrees on. We expect
        # the same set across rows since we filled per-model in lockstep.
        cols = ["Id", "Iq", "Phi_d_fem", "Phi_q_fem"]
        for e in ok:
            cols.extend([
                e["name"] + "_Phi_d_pred", e["name"] + "_Phi_q_pred",
                e["name"] + "_Phi_d_err", e["name"] + "_Phi_q_err",
            ])
        with open(os.path.join(val_dir, "off_grid_predictions.csv"),
                  "w", newline="") as f:
            import csv as csvmod
            w = csvmod.writer(f)
            w.writerow(cols)
            for r in rows_out:
                w.writerow([r.get(c, "") for c in cols])
    print(f"[wrote] {os.path.join(val_dir, 'off_grid_predictions.csv')}")

    # Plot.
    if T._HAS_MPL:
        try:
            plot_comparison(ok, X, Y, models_dir, val_dir)
            print(f"[wrote] {os.path.join(val_dir, 'off_grid_validation.png')}")
        except Exception as exc:
            print(f"[plot] failed: {exc}")
    print(f"\n[done] {n_models} models compared against {n_points} off-grid FEM points")
    return 0


def plot_comparison(ranklist, X, Y, models_dir, val_dir):
    import matplotlib.pyplot as plt
    if not ranklist:
        return
    n_show = min(8, len(ranklist))  # plot top-8 to keep legible
    show = ranklist[:n_show]

    fig, axes = plt.subplots(2, 2, figsize=(14, 11))

    # (0,0) Phi_d predicted vs true
    # (0,1) Phi_q predicted vs true
    # (1,0) Phi_d residual vs Id
    # (1,1) Phi_q residual vs Id
    markers = ["o", "s", "^", "v", "D", "P", "*", "X"]
    for k, e in enumerate(show):
        try:
            model = T._reload_model_for_plot(e, models_dir)
        except Exception:
            continue
        if model is None:
            continue
        try:
            pred = np.asarray(model.predict(X)).reshape(-1, 2)
        except Exception:
            continue
        m = markers[k % len(markers)]
        ax = axes[0][0]
        ax.scatter(Y[:, 0], pred[:, 0], s=42, marker=m, alpha=0.75,
                   label=f"{e['name']} (RMSE={e['off_grid']['rmse_phi_d']:.2e})")
        ax = axes[0][1]
        ax.scatter(Y[:, 1], pred[:, 1], s=42, marker=m, alpha=0.75,
                   label=f"{e['name']} (RMSE={e['off_grid']['rmse_phi_q']:.2e})")
        ax = axes[1][0]
        ax.scatter(X[:, 0], pred[:, 0] - Y[:, 0], s=34, marker=m, alpha=0.75,
                   label=e["name"])
        ax = axes[1][1]
        ax.scatter(X[:, 0], pred[:, 1] - Y[:, 1], s=34, marker=m, alpha=0.75,
                   label=e["name"])

    lim_d = (Y[:, 0].min(), Y[:, 0].max())
    lim_q = (Y[:, 1].min(), Y[:, 1].max())
    for lim, ax in [(lim_d, axes[0][0]), (lim_q, axes[0][1])]:
        ax.plot([lim[0], lim[1]], [lim[0], lim[1]], "k--", lw=0.7)
    axes[0][0].set_xlabel("Phi_d FEM (Wb)")
    axes[0][0].set_ylabel("Phi_d predicted (Wb)")
    axes[0][0].set_title("OFF-GRID validation: Phi_d predicted vs. true")
    axes[0][0].legend(fontsize=7)
    axes[0][1].set_xlabel("Phi_q FEM (Wb)")
    axes[0][1].set_ylabel("Phi_q predicted (Wb)")
    axes[0][1].set_title("OFF-GRID validation: Phi_q predicted vs. true")
    axes[0][1].legend(fontsize=7)
    axes[1][0].set_xlabel("Id (A)")
    axes[1][0].set_ylabel("Phi_d residual (Wb)")
    axes[1][0].set_title("Phi_d residual vs. Id (off-grid)")
    axes[1][0].legend(fontsize=7)
    axes[1][1].set_xlabel("Id (A)")
    axes[1][1].set_ylabel("Phi_q residual (Wb)")
    axes[1][1].set_title("Phi_q residual vs. Id (off-grid)")
    axes[1][1].legend(fontsize=7)
    fig.suptitle(
        f"Off-grid FEM validation - top {n_show} models by off-grid RMSE",
        fontsize=12,
    )
    plt.tight_layout()
    plt.savefig(os.path.join(val_dir, "off_grid_validation.png"), dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--truth", default=DEFAULT_TRUTH_CSV,
                   help="Path to off_grid_fem_results.csv from AEDT-side run. "
                        "Default: " + DEFAULT_TRUTH_CSV)
    p.add_argument("--models", default="out",
                   help="Output dir used by train_flux_map_comparison.py "
                        "(contains models/ and logs/). Default: out")
    p.add_argument("--out", default="out",
                   help="Where to write comparison outputs. Default: out")
    ns = p.parse_args()
    try:
        rc = main(ns)
    except FileNotFoundError as e:
        print(str(e))
        sys.exit(2)
    sys.exit(rc or 0)