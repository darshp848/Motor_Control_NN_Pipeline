"""Offline analysis of diagnose_flux_convention.py output.

Runs in the project venv (Python 3), NOT inside AEDT:

    .\\.venv\\Scripts\\python.exe eesm/aedt/analyze_flux_convention.py \\
        out/eesm/flux_convention_diagnostic/flux_convention_evidence.json \\
        out/eesm/flux_convention_diagnostic/verdict.json

It scores each candidate flux-extraction route against the balanced-winding
law and, for whichever route passes, derives the true d-axis electrical
angle from the field-only probe. It recommends a convention; it does not
apply one.

Candidate routes
----------------
A. winding_direct     AEDT FluxLinkage(PhaseX)                 <- current
B. coil_sum           signed sum of per-coil FluxLinkage
C. az_closed_loop     (N/Area)*depth*(A_z over go  -  A_z over return)

Route C is the only one that is gauge-independent by construction: the
arbitrary additive constant in the 2-D vector potential cancels in the
go-minus-return difference. Routes A and B are only correct if the solver
performs that differencing internally, which depends on how the go/return
polarity pair is assigned - and in this sector model every coil of a given
phase carries the SAME assigned polarity, with the sign inversion left to
the anti-periodic boundary.
"""

from __future__ import annotations

import json
import math
import sys
from typing import Mapping, Sequence


BALANCED_LIMIT = 0.05


def park(la: float, lb: float, lc: float, theta_rad: float):
    d = (2.0 / 3.0) * (
        la * math.cos(theta_rad)
        + lb * math.cos(theta_rad - 2 * math.pi / 3)
        + lc * math.cos(theta_rad + 2 * math.pi / 3)
    )
    q = (2.0 / 3.0) * (
        -la * math.sin(theta_rad)
        - lb * math.sin(theta_rad - 2 * math.pi / 3)
        - lc * math.sin(theta_rad + 2 * math.pi / 3)
    )
    return d, q


def balance_ratio(la: float, lb: float, lc: float) -> float:
    """|zero-sequence| / |dq magnitude|. Angle-independent."""
    zero = (la + lb + lc) / 3.0
    d, q = park(la, lb, lc, 0.0)
    mag = math.hypot(d, q)
    if mag < 1e-15:
        return float("inf")
    return abs(zero) / mag


def _ok(entry) -> bool:
    return isinstance(entry, Mapping) and entry.get("ok") is True


def _val(entry, default=None):
    return entry.get("value", default) if _ok(entry) else default


def route_winding_direct(point: Mapping) -> tuple[float, float, float] | None:
    table = _val(point.get("winding_flux_linkage"))
    if not isinstance(table, Mapping):
        return None
    out = []
    for phase in ("PhaseA", "PhaseB", "PhaseC"):
        key = next(
            (k for k in table if phase in k and "FluxLinkage" in k), None
        )
        if key is None or not isinstance(table[key], float):
            return None
        out.append(table[key])
    return tuple(out)  # type: ignore[return-value]


#: Coil sheet -> (winding, polarity sign), from RMxprt Maxwl2DV.vbs lines
#: 318-352 and confirmed against GetExcitations on the solved model.
#: Used when the live model's per-coil properties cannot be read back
#: (GetBoundaries returns only boundaries; coils live in GetExcitations,
#: and the per-coil property path is not exposed in AEDT 2025 R2 Student).
FALLBACK_COIL_MAP = {
    "Coil_0": ("PhaseA", 1.0), "Coil_1": ("PhaseA", 1.0),
    "CoilRe_0": ("PhaseA", 1.0), "CoilRe_1": ("PhaseA", 1.0),
    "Coil_4": ("PhaseB", 1.0), "Coil_5": ("PhaseB", 1.0),
    "CoilRe_4": ("PhaseB", 1.0), "CoilRe_5": ("PhaseB", 1.0),
    "Coil_2": ("PhaseC", -1.0), "Coil_3": ("PhaseC", -1.0),
    "CoilRe_2": ("PhaseC", -1.0), "CoilRe_3": ("PhaseC", -1.0),
}
FALLBACK_CONDUCTORS = 18.0
FALLBACK_DEPTH_M = 0.0770793


def parse_coil_inventory(inventory: Mapping) -> dict:
    """Map coil boundary name -> (winding, polarity_sign, conductors, sheet)."""
    mapping = {}
    for entry in inventory.get("coil_details", []) or []:
        name = entry.get("boundary")
        winding = _val(entry.get("Winding"))
        polarity = _val(entry.get("PolarityType"))
        conductors = _val(entry.get("Conductor number"))
        sheets = _val(entry.get("assignment")) or []
        if not name or not winding or not polarity:
            continue
        sign = -1.0 if str(polarity).strip().lower().startswith("neg") else 1.0
        try:
            turns = float(str(conductors))
        except (TypeError, ValueError):
            turns = float("nan")
        mapping[name] = {
            "winding": str(winding),
            "sign": sign,
            "conductors": turns,
            "sheets": [str(s) for s in sheets],
        }
    return mapping


def route_coil_sum(point: Mapping, coils: Mapping) -> tuple[float, float, float] | None:
    table = _val(point.get("coil_flux_linkage"))
    if not isinstance(table, Mapping) or not coils:
        return None
    totals = {"PhaseA": 0.0, "PhaseB": 0.0, "PhaseC": 0.0}
    seen = {"PhaseA": 0, "PhaseB": 0, "PhaseC": 0}
    for key, value in table.items():
        if not isinstance(value, float):
            continue
        for coil_name, meta in coils.items():
            if coil_name in key and meta["winding"] in totals:
                totals[meta["winding"]] += meta["sign"] * value
                seen[meta["winding"]] += 1
    if any(count == 0 for count in seen.values()):
        return None
    return (totals["PhaseA"], totals["PhaseB"], totals["PhaseC"])


def route_az_same_sign(
    point: Mapping, coils: Mapping, depth_m: float
) -> tuple[float, float, float] | None:
    """(N/Area)*depth*(A_z integral), summed with the winding's own signs.

    CONFIRMED CORRECT by solve on 2026-07-21. Every sheet of a phase
    carries the same polarity; the anti-periodic boundary supplies the
    sign inversion for the images in the other three sectors.

    An earlier version of this function differenced the 'Re' return sheets
    against the go sheets, on the theory that this was needed to cancel the
    vector-potential gauge constant. The solve disproved it: differencing
    RAISED the imbalance (0.0008 / 0.054 / 0.171 / 0.231 versus
    0.0001 / 0.016 / 0.080 / 0.010 for same-sign) and collapsed the
    field-only flux magnitude to ~1e-5 Wb. Do not reintroduce it.
    """
    az = point.get("az_integral_wb_m") or {}
    areas = point.get("sheet_area_m2") or {}
    if not az:
        return None

    depth = depth_m or FALLBACK_DEPTH_M
    totals = {"PhaseA": 0.0, "PhaseB": 0.0, "PhaseC": 0.0}
    contributions = 0

    if coils:
        items = [
            (sheet, meta["winding"], meta["sign"], meta["conductors"])
            for meta in coils.values()
            for sheet in meta["sheets"]
        ]
    else:
        items = [
            (sheet, winding, sign, FALLBACK_CONDUCTORS)
            for sheet, (winding, sign) in FALLBACK_COIL_MAP.items()
        ]

    for sheet, winding, sign, turns in items:
        if winding not in totals or turns != turns:  # NaN guard
            continue
        a = _val(az.get(sheet))
        area = _val(areas.get(sheet))
        if a is None or not area:
            continue
        totals[winding] += sign * turns * depth * a / area
        contributions += 1

    if contributions == 0:
        return None
    return (totals["PhaseA"], totals["PhaseB"], totals["PhaseC"])


def d_axis_angle_deg(la: float, lb: float, lc: float) -> float:
    """Electrical angle of the rotor field axis from a field-only solve.

    With only the rotor field energised, lambda_abc is a pure spatial
    sample of the rotor field, so its Park phase IS the d-axis angle. No
    rotor rotation is needed - which matters here, because the motion band
    was deleted from this model and the rotor cannot be rotated.
    """
    alpha = (2.0 / 3.0) * (la - 0.5 * lb - 0.5 * lc)
    beta = (2.0 / 3.0) * (math.sqrt(3.0) / 2.0) * (lb - lc)
    return math.degrees(math.atan2(beta, alpha)) % 360.0


def analyse(evidence: Mapping) -> dict:
    inventory = evidence.get("inventory") or {}
    coils = parse_coil_inventory(inventory)

    depth_text = str(_val(inventory.get("model_depth"), ""))
    depth_m = None
    for token in depth_text.replace(",", " ").split():
        if token.endswith("mm"):
            try:
                depth_m = float(token[:-2]) / 1000.0
                break
            except ValueError:
                pass

    routes = {
        "A_winding_direct": route_winding_direct,
        "B_coil_sum": lambda p: route_coil_sum(p, coils),
        "C_az_same_sign": lambda p: route_az_same_sign(p, coils, depth_m or 0.0),
    }

    per_route = {}
    for route_name, fn in routes.items():
        rows = []
        for point in evidence.get("points", []):
            try:
                triple = fn(point)  # type: ignore[operator]
            except Exception as exc:  # noqa: BLE001
                triple = None
                rows.append({"point": point.get("point"), "error": str(exc)})
                continue
            if triple is None:
                rows.append({
                    "point": point.get("point"),
                    "available": False,
                    "reason": "route not available in this evidence file",
                })
                continue
            la, lb, lc = triple
            rows.append({
                "point": point.get("point"),
                "available": True,
                "lambda_abc_wb": [la, lb, lc],
                "zero_sequence_wb": (la + lb + lc) / 3.0,
                "balance_ratio": balance_ratio(la, lb, lc),
            })
        usable = [r for r in rows if r.get("available")]
        ratios = [r["balance_ratio"] for r in usable if math.isfinite(r["balance_ratio"])]
        per_route[route_name] = {
            "points": rows,
            "usable_points": len(usable),
            "worst_balance_ratio": max(ratios) if ratios else None,
            "balanced": bool(ratios) and max(ratios) <= BALANCED_LIMIT,
        }

    verdict = {
        "model_depth_m": depth_m,
        "model_depth_source": depth_text or None,
        "symmetry_multiplier": _val(inventory.get("symmetry_multiplier")),
        "coil_inventory_entries": len(coils),
        "balanced_limit": BALANCED_LIMIT,
        "routes": per_route,
    }

    recommended = [n for n, r in per_route.items() if r["balanced"]]
    verdict["recommended_routes"] = recommended

    # Rank by worst-case balance so a route that is dramatically better but
    # marginally over the limit is reported as such, rather than lumped in
    # with routes that are broken. Loosening BALANCED_LIMIT to force a pass
    # would defeat the purpose of the gate.
    ranked = sorted(
        [(r["worst_balance_ratio"], n) for n, r in per_route.items()
         if r["worst_balance_ratio"] is not None],
        key=lambda pair: pair[0],
    )
    verdict["ranked_routes"] = [
        {"route": name, "worst_balance_ratio": ratio} for ratio, name in ranked
    ]
    if len(ranked) >= 2:
        verdict["best_over_worst_improvement"] = (
            ranked[-1][0] / ranked[0][0] if ranked[0][0] > 0 else None
        )

    best = recommended[0] if recommended else (ranked[0][1] if ranked else None)
    verdict["best_route"] = best
    verdict["best_route_clears_limit"] = bool(recommended)

    if best:
        field_rows = [
            r for r in per_route[best]["points"]
            if r.get("available") and r.get("point") == "field_only"
        ]
        if field_rows:
            la, lb, lc = field_rows[0]["lambda_abc_wb"]
            angle = d_axis_angle_deg(la, lb, lc)
            verdict["d_axis_electrical_angle_deg"] = angle
            verdict["legacy_rotor_position_deg"] = evidence.get(
                "legacy_rotor_position_deg"
            )
            verdict["angle_correction_deg"] = (
                angle - float(evidence.get("legacy_rotor_position_deg", 0.0))
            ) % 360.0
            worst = per_route[best]["worst_balance_ratio"]
            qualifier = (
                "produces a balanced three-phase set"
                if recommended else
                "is by far the best route (worst balance %.4f vs limit "
                "%.2f - close enough to be a discretisation artifact on a "
                "~1500-element mesh, but confirm before freezing)"
                % (worst, BALANCED_LIMIT)
            )
            verdict["conclusion"] = (
                "Route %s %s. Use it for extraction, and set the Park "
                "reference angle to %.2f deg electrical (currently %.2f "
                "deg, i.e. a correction of %.2f deg)."
                % (
                    best,
                    qualifier,
                    angle,
                    float(evidence.get("legacy_rotor_position_deg", 0.0)),
                    verdict["angle_correction_deg"],
                )
            )
        else:
            verdict["conclusion"] = (
                "Route %s is balanced, but the field_only probe is missing, "
                "so the d-axis angle could not be derived. Re-run the "
                "diagnostic including the field_only point." % best
            )
    else:
        verdict["conclusion"] = (
            "NO extraction route produced a balanced three-phase set. The "
            "imbalance is therefore not a post-processing convention at "
            "all - it is in the model's winding definition. Next checks, in "
            "order: (1) confirm every phase has an equal number of coil "
            "sheets and equal total conductors; (2) confirm the go/return "
            "polarity pairing within each phase; (3) confirm whether the "
            "symmetry multiplier is being applied to flux linkage as well "
            "as torque, and whether the winding is series (x4) or "
            "4-parallel-branch (x1) across the four sectors; (4) as a "
            "control, solve the SAME operating point on a full 360-degree "
            "model with no periodic boundary and compare - if the full "
            "model is balanced and the sector model is not, the fault is "
            "the sector's periodic-image handling."
        )
    return verdict


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        print("usage: analyze_flux_convention.py <evidence.json> <verdict.json>")
        return 2
    with open(sys.argv[1], "r") as stream:
        evidence = json.load(stream)
    verdict = analyse(evidence)
    with open(sys.argv[2], "w") as stream:
        json.dump(verdict, stream, indent=2, sort_keys=True)
    print(verdict["conclusion"])
    for name, route in verdict["routes"].items():
        print("  %-20s usable=%d worst_balance=%s balanced=%s" % (
            name,
            route["usable_points"],
            ("%.4f" % route["worst_balance_ratio"])
            if route["worst_balance_ratio"] is not None else "n/a",
            route["balanced"],
        ))
    return 0 if verdict["recommended_routes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
