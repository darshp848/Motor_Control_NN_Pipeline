"""Offline decision for the flux-linkage method comparison (CPython, no AEDT).

Reads out/eesm/flux_method_comparison/flux_method_evidence.json (produced by
compare_flux_methods.py) and applies the PILOT_FINDINGS.md decision rule:

  Adopt whichever flux method (native FluxLinkage vs route-C same-sign):
    1. closes torque within TORQUE_TOL at the UNSATURATED loaded point
       (pure_q_pos), and
    2. reproduces the route-C d-axis anchors: field-only projects to pure
       d-axis (|lam_q/lam_d| small) with lam_d increasing in If.

Prints a per-point table and a single recommended method, or an explicit
"inconclusive" with the reason. Makes NO file changes and freezes nothing;
adopting the method into flux_extraction_v2 / the exporter is a separate,
reviewed step once a method passes.
"""

from __future__ import annotations

import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
EVIDENCE = os.path.join(REPO_ROOT, "out", "eesm", "flux_method_comparison",
                        "flux_method_evidence.json")

TORQUE_TOL = 0.10          # 10% closure at the unsaturated loaded point
DAXIS_QOVERD_TOL = 5.0e-2  # |lam_q/lam_d| for a field-only point to read "pure d"
DECIDING_POINT = "pure_q_pos"
FIELD_ONLY_POINTS = ("field_only_3a", "field_only_5a")


def _get(evidence_path):
    if not os.path.exists(evidence_path):
        raise SystemExit("No evidence file at " + evidence_path
                         + "\nRun run_compare_flux_methods.ps1 first.")
    with open(evidence_path, "r") as stream:
        return json.load(stream)


def _method_ok(pt, tag):
    m = pt.get(tag)
    return bool(m and m.get("ok"))


def _fmt(x, spec="%+.4f"):
    return spec % x if isinstance(x, (int, float)) else str(x)


def daxis_check(evidence, tag):
    """Return (passes, detail) for the field-only d-axis anchors under `tag`."""
    lds = []
    detail = []
    for pt in evidence["points"]:
        if pt["point"] not in FIELD_ONLY_POINTS or not _method_ok(pt, tag):
            continue
        m = pt[tag]
        ld, lq = m["lambda_d_wb"], m["lambda_q_wb"]
        ratio = abs(lq / ld) if ld else float("inf")
        lds.append((pt["if_a"], ld))
        detail.append("%s: lam_d=%s lam_q=%s |q/d|=%.2e" % (
            pt["point"], _fmt(ld), _fmt(lq), ratio))
        if ratio > DAXIS_QOVERD_TOL:
            return False, "field-only not pure d-axis (" + detail[-1] + ")"
    if len(lds) >= 2:
        lds.sort()
        if not (lds[-1][1] > lds[0][1] > 0 or lds[-1][1] < lds[0][1] < 0):
            return False, "lam_d not monotone in If: " + str(lds)
    return True, "; ".join(detail)


def torque_closure(evidence, tag, point_name):
    for pt in evidence["points"]:
        if pt["point"] == point_name and _method_ok(pt, tag):
            r = pt[tag].get("torque_residual")
            return r
    return None


def main():
    evidence = _get(EVIDENCE)
    if evidence.get("status") != "collected":
        print("WARNING: evidence status is '%s', not 'collected'. Partial data."
              % evidence.get("status"))

    print("=== flux-method comparison ===")
    print("d-axis frame: %s deg | currents: %s\n"
          % (evidence.get("d_axis_electrical_deg"), evidence.get("currents_are")))

    hdr = "%-16s %10s %10s %9s | %10s %10s %9s" % (
        "point", "nat_ld", "nat_lq", "nat_Tres", "rc_ld", "rc_lq", "rc_Tres")
    print(hdr)
    print("-" * len(hdr))
    for pt in evidence["points"]:
        n = pt.get("native", {}); c = pt.get("route_c", {})
        def cell(m, key, spec="%+.4f"):
            return _fmt(m[key], spec) if m.get("ok") and key in m else "  --"
        print("%-16s %10s %10s %9s | %10s %10s %9s" % (
            pt["point"],
            cell(n, "lambda_d_wb"), cell(n, "lambda_q_wb"),
            cell(n, "torque_residual", "%+.3f"),
            cell(c, "lambda_d_wb"), cell(c, "lambda_q_wb"),
            cell(c, "torque_residual", "%+.3f")))

    print("\n=== decision rule ===")
    verdict = {}
    for tag, label in (("native", "native FluxLinkage(PhaseX)"),
                       ("route_c", "route-C same-sign")):
        tclose = torque_closure(evidence, tag, DECIDING_POINT)
        daxis_pass, daxis_detail = daxis_check(evidence, tag)
        tclose_pass = (tclose is not None and abs(tclose) <= TORQUE_TOL)
        verdict[tag] = {
            "label": label,
            "torque_residual_at_" + DECIDING_POINT: tclose,
            "torque_closes": tclose_pass,
            "daxis_anchors_ok": daxis_pass,
            "daxis_detail": daxis_detail,
            "adopt": tclose_pass and daxis_pass,
        }
        print("\n%s:" % label)
        print("  torque residual @ %s: %s (<= %.0f%%? %s)" % (
            DECIDING_POINT,
            _fmt(tclose, "%+.3f") if tclose is not None else "n/a",
            TORQUE_TOL * 100, tclose_pass))
        print("  d-axis anchors: %s (%s)" % (daxis_pass, daxis_detail))

    winners = [t for t in verdict if verdict[t]["adopt"]]
    print("\n=== VERDICT ===")
    if len(winners) == 1:
        w = winners[0]
        print("ADOPT: %s" % verdict[w]["label"])
        if w == "native":
            print("  -> Retire route-C same-sign for STATOR points; keep it only")
            print("     as an independent d-axis cross-check. Wire native")
            print("     FluxLinkage into the exporter, re-scope the zero-seq gate")
            print("     (NOTES 5), then re-run the 8-point pilot to re-validate")
            print("     before the 64-point campaign.")
        else:
            print("  -> route C closes torque after all; re-examine the pilot's")
            print("     torque calc for a unit/scale slip before trusting this.")
    elif not winners:
        print("INCONCLUSIVE: neither method passed both gates.")
        for t in verdict:
            v = verdict[t]
            print("  %s: torque_closes=%s daxis_ok=%s"
                  % (v["label"], v["torque_closes"], v["daxis_anchors_ok"]))
        print("  Next: inspect native FluxLinkage magnitudes vs route C; if")
        print("  native also fails torque closure, the issue is the single-pole")
        print("  sector torque/flux scaling, not the extraction method -- escalate")
        print("  to a co-energy torque cross-check (PILOT_FINDINGS.md option b).")
    else:
        print("BOTH methods pass -- prefer native FluxLinkage (AEDT winding-aware)")
        print("and keep route C as the d-axis cross-check.")

    out = os.path.join(os.path.dirname(EVIDENCE), "method_verdict.json")
    with open(out, "w") as stream:
        json.dump({"decision_tol": TORQUE_TOL, "deciding_point": DECIDING_POINT,
                   "verdict": verdict, "adopt": winners}, stream, indent=2)
    print("\nWrote " + out)


if __name__ == "__main__":
    main()
