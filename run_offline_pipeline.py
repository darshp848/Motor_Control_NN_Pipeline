"""One-command offline IPM pipeline (Stage 0 freeze).

raw FEM CSV
  -> train models
  -> off-grid compare (domain-stratified)
  -> promote inference winner (manifest policy)
  -> MTPA/FW LUT
  -> LUT audit commands + surrogate check
  -> out/run_manifest.json

Does not launch AEDT. Optional FEM stages remain separate scripts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from types import SimpleNamespace

from pipeline.manifest import (
    build_run_manifest,
    default_manifest_path,
    load_experiment_manifest,
    save_json,
    sha256_file,
)


def run_py(script, args_list, cwd=None):
    cmd = [sys.executable, script] + list(args_list)
    print("\n>>>", " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd or os.getcwd())
    if r.returncode != 0:
        raise RuntimeError(f"{script} failed with code {r.returncode}")
    return r.returncode


def maybe_hash(path):
    if path and os.path.exists(path):
        return sha256_file(path)
    return None


def select_inference_model(cfg, ranking_path, metrics_path):
    policy = cfg.get("inference_selection", "off_grid_in_domain")
    name = None
    if os.path.exists(ranking_path):
        with open(ranking_path, "r", encoding="utf-8") as f:
            ranking = json.load(f)
        if policy == "off_grid_in_domain":
            w = ranking.get("winner_off_grid_in_domain") or ranking.get("winner_off_grid")
            if w:
                name = w.get("name")
        elif policy == "off_grid_all":
            w = ranking.get("winner_off_grid_all") or ranking.get("winner_off_grid")
            if w:
                name = w.get("name")
        elif policy == "in_grid":
            name = None  # fall through to metrics
    if name is None and os.path.exists(metrics_path):
        with open(metrics_path, "r", encoding="utf-8") as f:
            results = json.load(f)
        ok = [r for r in results if r.get("status") == "ok"]
        ok.sort(key=lambda r: r["test"]["rmse_mean"])
        if ok:
            name = ok[0]["name"]
    return name, policy


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--config", default=default_manifest_path())
    p.add_argument("--skip-train", action="store_true",
                   help="Reuse existing out/models (still re-ranks and audits)")
    p.add_argument("--skip-mtpa", action="store_true",
                   help="Skip MTPA/LUT (use existing out/mtpa)")
    p.add_argument("--stages", default="all",
                   help="Comma list: train,compare,promote,mtpa,audit or all")
    ns = p.parse_args()

    cfg = load_experiment_manifest(ns.config)
    paths = cfg["paths"]
    seeds = cfg["seeds"]
    out_dir = paths.get("out_dir", "out")
    train_csv = paths["train_csv"]
    off_grid_csv = paths["off_grid_csv"]
    params_clean = paths.get("motor_params_clean", "data/motor_params_clean.json")
    mtpa_dir = paths.get("mtpa_dir", "out/mtpa")
    audit_dir = paths.get("audit_dir", "out/audit")

    stage_set = {s.strip() for s in ns.stages.split(",")}
    if "all" in stage_set:
        stage_set = {"train", "compare", "promote", "mtpa", "audit"}
    if ns.skip_train:
        stage_set.discard("train")
    if ns.skip_mtpa:
        stage_set.discard("mtpa")

    ran = []
    root = os.path.dirname(os.path.abspath(__file__)) or "."

    if "train" in stage_set:
        run_py(
            os.path.join(root, "train_flux_map_comparison.py"),
            ["--csv", train_csv, "--out", out_dir,
             "--seed", str(seeds.get("train_val_test_split", 0))],
        )
        ran.append("train")

    if "compare" in stage_set:
        run_py(
            os.path.join(root, "compare_off_grid_predictions.py"),
            ["--truth", off_grid_csv, "--train-csv", train_csv,
             "--models", out_dir, "--out", out_dir],
        )
        ran.append("compare")

    ranking_path = os.path.join(out_dir, "validation", "off_grid_ranking.json")
    metrics_path = os.path.join(out_dir, "logs", "metrics_summary.json")
    inference_model = None
    policy = cfg.get("inference_selection")

    if "promote" in stage_set:
        import train_flux_map_comparison as T
        inference_model, policy = select_inference_model(cfg, ranking_path, metrics_path)
        if not inference_model:
            raise RuntimeError("Could not select inference model for promotion")
        T.promote_inference_model(
            inference_model,
            os.path.join(out_dir, "models"),
        )
        ran.append("promote")
    else:
        inference_model, policy = select_inference_model(cfg, ranking_path, metrics_path)

    if "mtpa" in stage_set:
        run_py(
            os.path.join(root, "mtpa_field_weakening.py"),
            ["--params-json", params_clean, "--out", mtpa_dir],
        )
        ran.append("mtpa")

    if "audit" in stage_set:
        run_py(
            os.path.join(root, "audit_lut_scheduler.py"),
            [
                "--lookup", os.path.join(mtpa_dir, "reference_lookup.csv"),
                "--params", params_clean,
                "--out", audit_dir,
                "--seed", str(seeds.get("lut_audit_selection", 11)),
            ],
        )
        # Always write pending FEM join status
        run_py(
            os.path.join(root, "compare_lut_audit.py"),
            [
                "--commands", os.path.join(audit_dir, "lut_audit_commands.csv"),
                "--fem", os.path.join(audit_dir, "lut_audit_fem_results.csv"),
                "--out", audit_dir,
            ],
        )
        ran.append("audit")

    file_hashes = {
        "train_csv": maybe_hash(train_csv),
        "off_grid_csv": maybe_hash(off_grid_csv),
        "motor_params_clean": maybe_hash(params_clean),
        "metrics_summary": maybe_hash(metrics_path),
        "off_grid_ranking": maybe_hash(ranking_path),
        "reference_lookup": maybe_hash(os.path.join(mtpa_dir, "reference_lookup.csv")),
        "lut_audit_commands": maybe_hash(os.path.join(audit_dir, "lut_audit_commands.csv")),
        "inference_flux_map": maybe_hash(os.path.join(root, "inference_flux_map.py")),
    }
    if inference_model:
        for ext in (".pkl", ".pt", ".npz"):
            art = os.path.join(out_dir, "models", inference_model + ext)
            if os.path.exists(art):
                file_hashes["inference_artifact"] = sha256_file(art)
                break

    manifest = build_run_manifest(
        config=cfg,
        stages=ran,
        file_hashes={k: v for k, v in file_hashes.items() if v},
        seeds=seeds,
        inference_model=inference_model,
        extra={
            "inference_selection_policy": policy,
            "config_path": os.path.abspath(ns.config),
        },
    )
    out_manifest = os.path.join(out_dir, "run_manifest.json")
    save_json(out_manifest, manifest)
    print(f"\n[done] stages={ran}")
    print(f"[done] inference_model={inference_model} (policy={policy})")
    print(f"[done] {out_manifest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("PIPELINE FAILED:", exc)
        raise SystemExit(1)
