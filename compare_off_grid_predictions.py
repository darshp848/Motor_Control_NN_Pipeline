"""OFF-GRID MODEL COMPARISON (run in the venv python, NOT in AEDT).

Stage 0: labels each truth point as in_domain_interpolation / boundary /
extrapolation relative to the training map domain, and reports metrics
separately so interpolation and extrapolation are never mixed into one score.

Reads:
  data/off_grid_fem_results.csv  (Id, Iq, Phi_d, Phi_q [, domain_label])
  data/flux_map_fem.csv          (training domain inference)
  out/logs/metrics_summary.json

Writes:
  out/validation/off_grid_predictions.csv
  out/validation/off_grid_ranking.json
  out/validation/off_grid_by_domain.json
  out/validation/off_grid_fem_results_labeled.csv
  out/validation/off_grid_validation.png
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")

import train_flux_map_comparison as T
from pipeline.domain import (
    TrainingDomain,
    count_labels,
    default_ipm_training_domain,
    domain_from_training_xy,
    label_points,
)
from pipeline.data_qa import load_flux_csv

DEFAULT_TRUTH_CSV = os.path.join("data", "off_grid_fem_results.csv")
DEFAULT_TRAIN_CSV = os.path.join("data", "flux_map_fem.csv")


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
        pre_labels = None
        if "domain_label" in df.columns:
            pre_labels = [str(v) for v in df["domain_label"].tolist()]
    else:
        with open(csv_path, "r") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        header = lines[0].split(",")
        if header[:4] != ["Id", "Iq", "Phi_d", "Phi_q"]:
            raise RuntimeError("Expected header Id,Iq,Phi_d,Phi_q, got " + str(header))
        rows = np.array([[float(v) for v in ln.split(",")[:4]]
                          for ln in lines[1:]], dtype=np.float64)
        X, Y = rows[:, :2], rows[:, 2:4]
        pre_labels = None
        if len(header) >= 5 and header[4] == "domain_label":
            pre_labels = [ln.split(",")[4] for ln in lines[1:]]
    return X, Y, pre_labels


def per_model_metrics(y_true, y_pred):
    if y_true.shape[0] == 0:
        return {
            "n": 0,
            "rmse_phi_d": float("nan"),
            "rmse_phi_q": float("nan"),
            "rmse_mean": float("nan"),
            "r2_phi_d": float("nan"),
            "r2_phi_q": float("nan"),
            "r2_mean": float("nan"),
            "max_abs_err_phi_d": float("nan"),
            "max_abs_err_phi_q": float("nan"),
        }
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2, axis=0))
    ss_res = np.sum((y_true - y_pred) ** 2, axis=0)
    ss_tot = np.sum((y_true - y_true.mean(axis=0)) ** 2, axis=0) + 1e-12
    r2 = 1.0 - ss_res / ss_tot
    return {
        "n": int(y_true.shape[0]),
        "rmse_phi_d": float(rmse[0]),
        "rmse_phi_q": float(rmse[1]),
        "rmse_mean": float(rmse.mean()),
        "r2_phi_d": float(r2[0]),
        "r2_phi_q": float(r2[1]),
        "r2_mean": float(r2.mean()),
        "max_abs_err_phi_d": float(np.max(np.abs(y_true[:, 0] - y_pred[:, 0]))),
        "max_abs_err_phi_q": float(np.max(np.abs(y_true[:, 1] - y_pred[:, 1]))),
    }


def resolve_training_domain(train_csv: str) -> TrainingDomain:
    if os.path.exists(train_csv):
        X_tr, _, issues = load_flux_csv(train_csv)
        if issues:
            print("[domain] train CSV issues: " + "; ".join(issues))
        return domain_from_training_xy(X_tr)
    print("[domain] train CSV missing; using default IPM domain [-300,0]x[0,300]")
    return default_ipm_training_domain()


def main(args):
    truth_csv = args.truth
    models_root = args.models
    out_dir = args.out
    val_dir = os.path.join(out_dir, "validation")
    os.makedirs(val_dir, exist_ok=True)

    domain = resolve_training_domain(args.train_csv)
    print(f"[domain] training Id [{domain.id_min}, {domain.id_max}], "
          f"Iq [{domain.iq_min}, {domain.iq_max}]")

    print(f"[load] truth CSV: {truth_csv}")
    X, Y, pre_labels = load_truth(truth_csv)
    n_points = X.shape[0]
    if pre_labels is not None and len(pre_labels) == n_points:
        labels = pre_labels
        print("[domain] using domain_label column from truth CSV")
    else:
        labels = label_points(X, domain)
        print("[domain] labels computed from training domain")
    label_counts = count_labels(labels)
    print(f"[domain] counts: {label_counts}")

    print(f"[load] {n_points} off-grid points, "
          f"Id range [{X[:,0].min():.2f}, {X[:,0].max():.2f}], "
          f"Iq range [{X[:,1].min():.2f}, {X[:,1].max():.2f}]")

    # Labeled truth copy for freeze / downstream.
    labeled_path = os.path.join(val_dir, "off_grid_fem_results_labeled.csv")
    if T._HAS_PANDAS:
        import pandas as pd
        pd.DataFrame({
            "Id": X[:, 0], "Iq": X[:, 1],
            "Phi_d": Y[:, 0], "Phi_q": Y[:, 1],
            "domain_label": labels,
        }).to_csv(labeled_path, index=False)
    else:
        with open(labeled_path, "w", newline="") as f:
            import csv as csvmod
            w = csvmod.writer(f)
            w.writerow(["Id", "Iq", "Phi_d", "Phi_q", "domain_label"])
            for i in range(n_points):
                w.writerow([X[i, 0], X[i, 1], Y[i, 0], Y[i, 1], labels[i]])
    # Also write under data/ for the freeze snapshot if requested.
    data_labeled = os.path.join("data", "off_grid_fem_results_labeled.csv")
    try:
        import shutil
        shutil.copy2(labeled_path, data_labeled)
        print(f"[wrote] {data_labeled}")
    except Exception as exc:
        print(f"[warn] could not copy labeled CSV to data/: {exc}")
    print(f"[wrote] {labeled_path}")

    summary_path = os.path.join(models_root, "logs", "metrics_summary.json")
    if not os.path.exists(summary_path):
        raise FileNotFoundError(
            "metrics_summary.json not found at: " + summary_path + "\n"
            "Run train_flux_map_comparison.py first."
        )
    with open(summary_path, "r") as f:
        in_grid_results = json.load(f)
    models_dir = os.path.join(models_root, "models")

    domain_keys = (
        "all",
        "in_domain_interpolation",
        "boundary",
        "extrapolation",
    )
    masks = {
        "all": np.ones(n_points, dtype=bool),
        "in_domain_interpolation": np.array(
            [lab == "in_domain_interpolation" for lab in labels]
        ),
        "boundary": np.array([lab == "boundary" for lab in labels]),
        "extrapolation": np.array([lab == "extrapolation" for lab in labels]),
    }

    rows_out = []
    for i in range(n_points):
        rows_out.append({
            "Id": X[i, 0], "Iq": X[i, 1],
            "Phi_d_fem": Y[i, 0], "Phi_q_fem": Y[i, 1],
            "domain_label": labels[i],
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
            leaderboard.append({"name": m_name, "status": "no_loader"})
            continue
        try:
            pred = np.asarray(model.predict(X)).reshape(-1, 2)
        except Exception as exc:
            print(f"  predict failed: {exc}")
            leaderboard.append({
                "name": m_name, "status": "predict_failed", "error": str(exc),
            })
            continue

        metrics_by_domain = {}
        for key in domain_keys:
            msk = masks[key]
            metrics_by_domain[key] = per_model_metrics(Y[msk], pred[msk])

        m_all = metrics_by_domain["all"]
        m_interp = metrics_by_domain["in_domain_interpolation"]
        m_extrap = metrics_by_domain["extrapolation"]
        print(f"  all      RMSE mean={m_all['rmse_mean']:.5e} (n={m_all['n']})")
        print(f"  in-domain interp RMSE mean={m_interp['rmse_mean']:.5e} "
              f"(n={m_interp['n']})")
        print(f"  extrap   RMSE mean={m_extrap['rmse_mean']:.5e} "
              f"(n={m_extrap['n']})")
        print(f"  in-grid  test RMSE mean: {r['test']['rmse_mean']:.5e}")

        for i in range(n_points):
            tag = m_name
            rows_out[i][tag + "_Phi_d_pred"] = float(pred[i, 0])
            rows_out[i][tag + "_Phi_q_pred"] = float(pred[i, 1])
            rows_out[i][tag + "_Phi_d_err"] = float(pred[i, 0] - Y[i, 0])
            rows_out[i][tag + "_Phi_q_err"] = float(pred[i, 1] - Y[i, 1])

        # Ranking keys: prefer in-domain interp; fall back to all if empty.
        rank_key = (
            m_interp["rmse_mean"]
            if m_interp["n"] > 0 and np.isfinite(m_interp["rmse_mean"])
            else m_all["rmse_mean"]
        )
        leaderboard.append({
            "name": m_name,
            "status": "ok",
            "in_grid_test": r.get("test", {}),
            "off_grid": m_all,
            "off_grid_by_domain": metrics_by_domain,
            "off_grid_rmse_mean": m_all["rmse_mean"],
            "off_grid_in_domain_rmse_mean": rank_key,
            "off_grid_extrap_rmse_mean": m_extrap["rmse_mean"],
        })
        n_models += 1

    ok = [e for e in leaderboard if e.get("status") == "ok"]
    ok_all = sorted(ok, key=lambda e: e["off_grid_rmse_mean"])
    ok_in = sorted(ok, key=lambda e: e["off_grid_in_domain_rmse_mean"])
    ok_ex = sorted(
        [e for e in ok if np.isfinite(e.get("off_grid_extrap_rmse_mean", float("nan")))],
        key=lambda e: e["off_grid_extrap_rmse_mean"],
    )

    print("\n=== LEADERBOARD: in-domain interpolation off-grid RMSE (primary) ===")
    for i, e in enumerate(ok_in, 1):
        mark = "  <== in-domain winner" if i == 1 else ""
        print(f"  {i:2d}. {e['name']:<22} "
              f"in_domain_rmse={e['off_grid_in_domain_rmse_mean']:.5e} "
              f"all_rmse={e['off_grid_rmse_mean']:.5e} "
              f"in_grid_test={e['in_grid_test']['rmse_mean']:.5e}{mark}")

    print("\n=== LEADERBOARD: mixed all-points off-grid RMSE (historical) ===")
    for i, e in enumerate(ok_all, 1):
        mark = "  <== mixed winner" if i == 1 else ""
        print(f"  {i:2d}. {e['name']:<22} "
              f"all_rmse={e['off_grid_rmse_mean']:.5e}{mark}")

    if ok_ex and ok_ex[0].get("off_grid_by_domain", {}).get("extrapolation", {}).get("n", 0) > 0:
        print("\n=== LEADERBOARD: extrapolation-only off-grid RMSE (secondary) ===")
        for i, e in enumerate(ok_ex, 1):
            mark = "  <== extrap winner" if i == 1 else ""
            print(f"  {i:2d}. {e['name']:<22} "
                  f"extrap_rmse={e['off_grid_extrap_rmse_mean']:.5e}{mark}")

    ranking = {
        "n_truth_points": n_points,
        "truth_csv": os.path.abspath(truth_csv),
        "training_domain": domain.to_dict(),
        "domain_label_counts": label_counts,
        "ranking_primary": "off_grid_in_domain_rmse_mean",
        "leaderboard": leaderboard,
        "leaderboard_in_domain_sorted": ok_in,
        "leaderboard_all_sorted": ok_all,
        "leaderboard_extrap_sorted": ok_ex,
        "winner_off_grid_in_domain": ok_in[0] if ok_in else None,
        "winner_off_grid_all": ok_all[0] if ok_all else None,
        "winner_off_grid": ok_in[0] if ok_in else (ok_all[0] if ok_all else None),
        "note": (
            "Historical mixed ranking contaminated Id>0 extrapolation into "
            "'generalization'. Primary winner is in-domain interpolation."
        ),
    }
    with open(os.path.join(val_dir, "off_grid_ranking.json"), "w") as f:
        json.dump(ranking, f, indent=2)
    with open(os.path.join(val_dir, "off_grid_by_domain.json"), "w") as f:
        json.dump({
            "domain_label_counts": label_counts,
            "training_domain": domain.to_dict(),
            "per_model": [
                {
                    "name": e["name"],
                    "by_domain": e.get("off_grid_by_domain"),
                }
                for e in ok
            ],
        }, f, indent=2)
    print(f"\n[wrote] {os.path.join(val_dir, 'off_grid_ranking.json')}")
    print(f"[wrote] {os.path.join(val_dir, 'off_grid_by_domain.json')}")

    if T._HAS_PANDAS:
        import pandas as pd
        pd.DataFrame(rows_out).to_csv(
            os.path.join(val_dir, "off_grid_predictions.csv"), index=False
        )
    else:
        cols = ["Id", "Iq", "Phi_d_fem", "Phi_q_fem", "domain_label"]
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

    if T._HAS_MPL:
        try:
            plot_comparison(ok_in, X, Y, labels, models_dir, val_dir)
            print(f"[wrote] {os.path.join(val_dir, 'off_grid_validation.png')}")
        except Exception as exc:
            print(f"[plot] failed: {exc}")
    print(f"\n[done] {n_models} models compared against {n_points} off-grid FEM points")
    return 0


def plot_comparison(ranklist, X, Y, labels, models_dir, val_dir):
    import matplotlib.pyplot as plt
    if not ranklist:
        return
    n_show = min(8, len(ranklist))
    show = ranklist[:n_show]
    labels_arr = np.asarray(labels)
    is_extrap = labels_arr == "extrapolation"

    # Rebuild minimal result dicts for the train reload helper.
    summary_path = os.path.join(os.path.dirname(models_dir), "logs", "metrics_summary.json")
    by_name = {}
    if os.path.exists(summary_path):
        with open(summary_path, "r") as f:
            for r in json.load(f):
                by_name[r.get("name")] = r

    fig, axes = plt.subplots(2, 2, figsize=(14, 11))
    markers = ["o", "s", "^", "v", "D", "P", "*", "X"]
    for k, e in enumerate(show):
        r = by_name.get(e["name"], {
            "name": e["name"],
            "status": "ok",
            "artifact_path": _artifact_for(e["name"], models_dir),
        })
        try:
            model = T._reload_model_for_plot(r, models_dir)
        except Exception:
            continue
        if model is None:
            continue
        try:
            pred = np.asarray(model.predict(X)).reshape(-1, 2)
        except Exception:
            continue
        m = markers[k % len(markers)]
        axes[0][0].scatter(Y[~is_extrap, 0], pred[~is_extrap, 0], s=42, marker=m,
                           alpha=0.75, label=e["name"])
        axes[0][1].scatter(Y[~is_extrap, 1], pred[~is_extrap, 1], s=42, marker=m,
                           alpha=0.75, label=e["name"])
        if np.any(is_extrap):
            axes[0][0].scatter(Y[is_extrap, 0], pred[is_extrap, 0], s=42, marker=m,
                               alpha=0.45, facecolors="none")
            axes[0][1].scatter(Y[is_extrap, 1], pred[is_extrap, 1], s=42, marker=m,
                               alpha=0.45, facecolors="none")
        axes[1][0].scatter(X[~is_extrap, 0], (pred - Y)[~is_extrap, 0],
                           s=34, marker=m, alpha=0.75, label=e["name"])
        axes[1][1].scatter(X[~is_extrap, 0], (pred - Y)[~is_extrap, 1],
                           s=34, marker=m, alpha=0.75, label=e["name"])
        if np.any(is_extrap):
            axes[1][0].scatter(X[is_extrap, 0], (pred - Y)[is_extrap, 0],
                               s=34, marker=m, alpha=0.45, facecolors="none")
            axes[1][1].scatter(X[is_extrap, 0], (pred - Y)[is_extrap, 1],
                               s=34, marker=m, alpha=0.45, facecolors="none")

    lim_d = (Y[:, 0].min(), Y[:, 0].max())
    lim_q = (Y[:, 1].min(), Y[:, 1].max())
    for lim, ax in [(lim_d, axes[0][0]), (lim_q, axes[0][1])]:
        ax.plot([lim[0], lim[1]], [lim[0], lim[1]], "k--", lw=0.7)
    axes[0][0].set_xlabel("Phi_d FEM (Wb)")
    axes[0][0].set_ylabel("Phi_d predicted (Wb)")
    axes[0][0].set_title("Off-grid: Phi_d (filled=interp, open=extrap)")
    axes[0][0].legend(fontsize=7)
    axes[0][1].set_xlabel("Phi_q FEM (Wb)")
    axes[0][1].set_ylabel("Phi_q predicted (Wb)")
    axes[0][1].set_title("Off-grid: Phi_q (filled=interp, open=extrap)")
    axes[0][1].legend(fontsize=7)
    axes[1][0].set_xlabel("Id (A)")
    axes[1][0].set_ylabel("Phi_d residual (Wb)")
    axes[1][0].set_title("Phi_d residual vs Id")
    axes[1][0].axvline(0.0, color="k", ls=":", lw=0.8)
    axes[1][0].legend(fontsize=7)
    axes[1][1].set_xlabel("Id (A)")
    axes[1][1].set_ylabel("Phi_q residual (Wb)")
    axes[1][1].set_title("Phi_q residual vs Id")
    axes[1][1].axvline(0.0, color="k", ls=":", lw=0.8)
    axes[1][1].legend(fontsize=7)
    fig.suptitle(
        f"Off-grid FEM validation - top {n_show} by in-domain RMSE "
        f"(open markers = Id extrapolation)",
        fontsize=11,
    )
    plt.tight_layout()
    plt.savefig(os.path.join(val_dir, "off_grid_validation.png"), dpi=140)
    plt.close(fig)


def _artifact_for(name, models_dir):
    for ext in (".pkl", ".pt", ".npz"):
        p = os.path.join(models_dir, name + ext)
        if os.path.exists(p):
            return p
    return os.path.join(models_dir, name + ".pkl")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--truth", default=DEFAULT_TRUTH_CSV,
                   help="Path to off_grid_fem_results.csv from AEDT-side run. "
                        "Default: " + DEFAULT_TRUTH_CSV)
    p.add_argument("--train-csv", default=DEFAULT_TRAIN_CSV,
                   help="Training map used to define the domain. Default: "
                        + DEFAULT_TRAIN_CSV)
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
