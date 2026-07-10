"""Prospective LUT / scheduler audit (offline).

Selects a fixed, seeded subset of reference_lookup rows and evaluates the
surrogate at the scheduled (Id*, Iq*) for torque/voltage consistency with
(ω, T*). Writes a FEM command list for optional AEDT re-solve.

This does NOT require AEDT. FEM closure is optional:
  1) this script -> out/audit/lut_audit_commands.csv
  2) validate_lut_audit_fem.py (AEDT) -> FEM fluxes
  3) compare_lut_audit.py -> T_fem vs T*
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

from pipeline.manifest import sha256_file
from pipeline.physics import electromagnetic_torque, rpm_mech_to_we, stator_voltage_dq, v_max_svpwm


def load_lookup(path):
    rows = []
    with open(path, "r", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({
                "rpm_mech": float(row["rpm_mech"]),
                "T_ref_Nm": float(row["T_ref_Nm"]),
                "Id_ref_A": _f(row.get("Id_ref_A")),
                "Iq_ref_A": _f(row.get("Iq_ref_A")),
                "Is_norm_A": _f(row.get("Is_norm_A")),
                "status": str(row.get("status", "")),
            })
    return rows


def _f(v):
    if v is None or v == "" or str(v).lower() == "nan":
        return float("nan")
    return float(v)


def load_params(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def stratified_select(rows, seed, n_mtpa=8, n_fw=4, n_infeasible=2):
    rng = np.random.default_rng(seed)
    by_status = defaultdict(list)
    for i, row in enumerate(rows):
        by_status[row["status"]].append(i)

    selected = []

    def take(status, n, prefer_near_base=False, base_rpm=1800.0):
        idxs = list(by_status.get(status, []))
        if not idxs:
            return
        if prefer_near_base:
            idxs = sorted(
                idxs,
                key=lambda i: abs(rows[i]["rpm_mech"] - base_rpm),
            )
        # Deterministic subsample via RNG permutation of eligible indices.
        perm = rng.permutation(len(idxs))
        chosen = [idxs[int(j)] for j in perm[:n]]
        if prefer_near_base:
            # Re-sort chosen for stability: nearest base first.
            chosen = sorted(chosen, key=lambda i: abs(rows[i]["rpm_mech"] - base_rpm))[:n]
        for i in chosen:
            selected.append(i)

    take("mtpa", n_mtpa, prefer_near_base=True)
    take("fw", n_fw)
    # Some runs only have infeasible / fw_search_failed
    take("infeasible", n_infeasible)
    if len([i for i in selected if rows[i]["status"] == "infeasible"]) < n_infeasible:
        take("fw_search_failed", n_infeasible)

    # Unique, stable order by index
    selected = sorted(set(selected))
    return selected


def main(args):
    lookup_path = args.lookup
    if not os.path.exists(lookup_path):
        raise FileNotFoundError(
            f"LUT not found: {lookup_path}. Run mtpa_field_weakening.py first."
        )
    params_path = args.params
    if not os.path.exists(params_path):
        for cand in ("data/motor_params_clean.json", "out/mtpa/motor_params_used.json",
                     "data/motor_params.json"):
            if os.path.exists(cand):
                params_path = cand
                break
    params = load_params(params_path)
    pole_pairs = int(params.get("pole_pairs") or int(params.get("poles", 4)) // 2)
    rs = float(params.get("rs_ohm", 2.15938))
    vdc = float(params.get("vdc_v", 311.0))
    flux_scale = float(params.get("flux_scale", 1.0))
    v_max = v_max_svpwm(vdc)

    rows = load_lookup(lookup_path)
    idxs = stratified_select(
        rows, seed=args.seed,
        n_mtpa=args.n_mtpa, n_fw=args.n_fw, n_infeasible=args.n_infeasible,
    )
    print(f"[audit] selected {len(idxs)} LUT rows (seed={args.seed})")

    # Load surrogate
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import inference_flux_map as inf

    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    commands = []
    surrogate_rows = []
    for rank, i in enumerate(idxs):
        row = rows[i]
        cmd_id = f"lut_audit_{rank:03d}"
        id_ref = row["Id_ref_A"]
        iq_ref = row["Iq_ref_A"]
        status = row["status"]
        rpm = row["rpm_mech"]
        t_ref = row["T_ref_Nm"]
        we = rpm_mech_to_we(rpm, pole_pairs)

        entry = {
            "command_id": cmd_id,
            "lut_row_index": i,
            "rpm_mech": rpm,
            "T_ref_Nm": t_ref,
            "Id_ref_A": id_ref,
            "Iq_ref_A": iq_ref,
            "status": status,
            "omega_e_rad_s": we,
            "pole_pairs": pole_pairs,
            "flux_scale": flux_scale,
            "v_max_v": v_max,
            "rs_ohm": rs,
            "needs_fem": status in ("mtpa", "fw") and math.isfinite(id_ref) and math.isfinite(iq_ref),
        }
        commands.append(entry)

        srow = dict(entry)
        if entry["needs_fem"]:
            phi_d, phi_q = inf.predict(float(id_ref), float(iq_ref))
            phi_d_s = phi_d * flux_scale
            phi_q_s = phi_q * flux_scale
            t_surr = float(electromagnetic_torque(id_ref, iq_ref, phi_d_s, phi_q_s, pole_pairs))
            v_mag, vd, vq = stator_voltage_dq(id_ref, iq_ref, phi_d_s, phi_q_s, we, rs)
            srow.update({
                "Phi_d_raw": phi_d,
                "Phi_q_raw": phi_q,
                "Phi_d_scaled": phi_d_s,
                "Phi_q_scaled": phi_q_s,
                "T_surrogate_Nm": t_surr,
                "T_error_Nm": t_surr - t_ref,
                "T_rel_error": (t_surr - t_ref) / max(abs(t_ref), 1e-6),
                "V_surrogate_V": float(v_mag),
                "V_margin_V": v_max - float(v_mag),
                "voltage_ok": bool(float(v_mag) <= v_max * 1.001),
            })
        else:
            srow.update({
                "Phi_d_raw": float("nan"),
                "Phi_q_raw": float("nan"),
                "T_surrogate_Nm": float("nan"),
                "T_error_Nm": float("nan"),
                "note": "infeasible_or_missing_current; policy check only",
            })
        surrogate_rows.append(srow)

    cmd_path = os.path.join(out_dir, "lut_audit_commands.csv")
    surr_path = os.path.join(out_dir, "lut_audit_surrogate.csv")
    _write_dict_csv(cmd_path, commands)
    _write_dict_csv(surr_path, surrogate_rows)

    feasible = [r for r in surrogate_rows if r.get("needs_fem")]
    t_errs = [abs(r["T_error_Nm"]) for r in feasible if math.isfinite(r.get("T_error_Nm", float("nan")))]
    report = {
        "status": "ok",
        "seed": args.seed,
        "n_commands": len(commands),
        "n_fem_candidates": sum(1 for c in commands if c["needs_fem"]),
        "params_path": os.path.abspath(params_path),
        "lookup_path": os.path.abspath(lookup_path),
        "lookup_sha256": sha256_file(lookup_path) if os.path.exists(lookup_path) else None,
        "params_sha256": sha256_file(params_path) if os.path.exists(params_path) else None,
        "pole_pairs": pole_pairs,
        "flux_scale": flux_scale,
        "v_max_v": v_max,
        "surrogate_torque_abs_error_mean": float(np.mean(t_errs)) if t_errs else None,
        "surrogate_torque_abs_error_max": float(np.max(t_errs)) if t_errs else None,
        "fem_results_status": "pending_optional_aedt",
        "next_steps": [
            "Run validate_lut_audit_fem.py in AEDT with lut_audit_commands.csv",
            "Run compare_lut_audit.py to join FEM fluxes and compute T_fem vs T*",
        ],
        "commands_csv": cmd_path,
        "surrogate_csv": surr_path,
    }
    report_path = os.path.join(out_dir, "lut_audit_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(f"[wrote] {cmd_path}")
    print(f"[wrote] {surr_path}")
    print(f"[wrote] {report_path}")
    if t_errs:
        print(f"[surrogate] mean |T_err|={np.mean(t_errs):.4f} N.m "
              f"max={np.max(t_errs):.4f} N.m on {len(t_errs)} feasible points")
    return 0


def _write_dict_csv(path, rows):
    if not rows:
        with open(path, "w", newline="") as f:
            f.write("")
        return
    # Union of keys, stable-ish order
    keys = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                keys.append(k)
                seen.add(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--lookup", default=os.path.join("out", "mtpa", "reference_lookup.csv"))
    p.add_argument("--params", default=os.path.join("data", "motor_params_clean.json"))
    p.add_argument("--out", default=os.path.join("out", "audit"))
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--n-mtpa", type=int, default=8)
    p.add_argument("--n-fw", type=int, default=4)
    p.add_argument("--n-infeasible", type=int, default=2)
    ns = p.parse_args()
    try:
        raise SystemExit(main(ns) or 0)
    except FileNotFoundError as e:
        print(str(e))
        raise SystemExit(2)
