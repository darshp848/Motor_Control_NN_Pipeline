"""Join FEM audit fluxes with LUT commands and report torque/voltage errors.

Inputs:
  out/audit/lut_audit_commands.csv
  out/audit/lut_audit_surrogate.csv  (optional, for side-by-side)
  FEM truth CSV from validate_lut_audit_fem.py:
      Id,Iq,Phi_d,Phi_q,command_id   (or same order as commands)

If FEM CSV is missing, exits with status pending and a clear message.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys

import numpy as np

from pipeline.physics import electromagnetic_torque, rpm_mech_to_we, stator_voltage_dq


def load_csv_dicts(path):
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main(args):
    cmd_path = args.commands
    fem_path = args.fem
    if not os.path.exists(cmd_path):
        raise FileNotFoundError(cmd_path)
    if not os.path.exists(fem_path):
        report = {
            "status": "pending_fem",
            "message": (
                "FEM audit CSV not found. Protocol is frozen: generate "
                "commands with audit_lut_scheduler.py, then run "
                "validate_lut_audit_fem.py in AEDT."
            ),
            "commands_csv": os.path.abspath(cmd_path),
            "expected_fem_csv": os.path.abspath(fem_path),
        }
        os.makedirs(args.out, exist_ok=True)
        out_json = os.path.join(args.out, "lut_audit_fem_join.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
        print(report["message"])
        print(f"[wrote] {out_json}")
        return 0

    commands = load_csv_dicts(cmd_path)
    fem_rows = load_csv_dicts(fem_path)
    fem_by_id = {}
    for r in fem_rows:
        key = r.get("command_id")
        if key:
            fem_by_id[key] = r
    # Fallback: zip by order
    joined = []
    for i, cmd in enumerate(commands):
        if not _truthy(cmd.get("needs_fem")):
            continue
        fr = fem_by_id.get(cmd["command_id"])
        if fr is None and i < len(fem_rows):
            fr = fem_rows[i]
        if fr is None:
            joined.append({**cmd, "status_join": "missing_fem"})
            continue
        id_a = float(cmd["Id_ref_A"])
        iq_a = float(cmd["Iq_ref_A"])
        phi_d = float(fr["Phi_d"]) * float(cmd.get("flux_scale", 1.0))
        phi_q = float(fr["Phi_q"]) * float(cmd.get("flux_scale", 1.0))
        pp = int(float(cmd.get("pole_pairs", 2)))
        t_fem = float(electromagnetic_torque(id_a, iq_a, phi_d, phi_q, pp))
        t_ref = float(cmd["T_ref_Nm"])
        we = float(cmd.get("omega_e_rad_s") or rpm_mech_to_we(float(cmd["rpm_mech"]), pp))
        rs = float(cmd.get("rs_ohm", 2.15938))
        v_mag, _, _ = stator_voltage_dq(id_a, iq_a, phi_d, phi_q, we, rs)
        joined.append({
            **cmd,
            "Phi_d_fem_raw": float(fr["Phi_d"]),
            "Phi_q_fem_raw": float(fr["Phi_q"]),
            "Phi_d_fem_scaled": phi_d,
            "Phi_q_fem_scaled": phi_q,
            "T_fem_Nm": t_fem,
            "T_ref_Nm": t_ref,
            "T_error_Nm": t_fem - t_ref,
            "T_rel_error": (t_fem - t_ref) / max(abs(t_ref), 1e-6),
            "V_fem_V": float(v_mag),
            "status_join": "ok",
        })

    os.makedirs(args.out, exist_ok=True)
    out_csv = os.path.join(args.out, "lut_audit_fem_join.csv")
    if joined:
        keys = list(joined[0].keys())
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(joined)

    ok = [j for j in joined if j.get("status_join") == "ok"]
    t_errs = [abs(j["T_error_Nm"]) for j in ok]
    report = {
        "status": "ok" if ok else "no_joined_points",
        "n_joined": len(ok),
        "mean_abs_T_error_Nm": float(np.mean(t_errs)) if t_errs else None,
        "max_abs_T_error_Nm": float(np.max(t_errs)) if t_errs else None,
        "join_csv": out_csv if joined else None,
    }
    out_json = os.path.join(args.out, "lut_audit_fem_join.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(json.dumps(report, indent=2))
    return 0


def _truthy(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--commands", default=os.path.join("out", "audit", "lut_audit_commands.csv"))
    p.add_argument("--fem", default=os.path.join("out", "audit", "lut_audit_fem_results.csv"))
    p.add_argument("--out", default=os.path.join("out", "audit"))
    ns = p.parse_args()
    try:
        raise SystemExit(main(ns) or 0)
    except FileNotFoundError as e:
        print(str(e))
        raise SystemExit(2)
