#!/usr/bin/env python
"""T_even vs |iq| at fixed If=2 A. Distinguishes detent, iq^2, and WST bias."""

from __future__ import annotations

import json
import os
import sys

_EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_EESM_ROOT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from eesm.femm import extract, geometry, runtime
from eesm.femm.config import DEFAULT_CONFIG
from eesm.femm.extract import decompose_mirror_torque

IQS = (0.0, 15.0, 30.0, 45.0, 60.0)
IF_A = 2.0
OUT = os.path.join(_REPO_ROOT, "out", "eesm", "femm_f1_even_sweep_20260812")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    handle = runtime.resolve_femm()
    geometry.open_and_build(handle, os.path.join(OUT, "eesm_sector.fem"),
                            DEFAULT_CONFIG)
    rows = []
    try:
        for iq in IQS:
            pos = extract.extract_point(handle, 0.0, iq, IF_A, cfg=DEFAULT_CONFIG)
            if iq == 0.0:
                parts = {
                    "even_nm": pos["torque_fem_nm"],
                    "odd_nm": 0.0,
                    "asymmetry_pct": 0.0,
                    "identity_even_nm": pos["torque_identity_nm"],
                }
                neg = None
            else:
                neg = extract.extract_point(
                    handle, 0.0, -iq, IF_A, cfg=DEFAULT_CONFIG)
                parts = decompose_mirror_torque(
                    pos["torque_fem_nm"], neg["torque_fem_nm"])
                id_parts = decompose_mirror_torque(
                    pos["torque_identity_nm"], neg["torque_identity_nm"])
                parts["identity_even_nm"] = id_parts["even_nm"]
                parts["identity_odd_nm"] = id_parts["odd_nm"]
                parts["k_odd"] = (
                    parts["odd_nm"] / id_parts["odd_nm"]
                    if id_parts["odd_nm"] else None
                )
            closer = getattr(handle, "mo_close", None)
            if callable(closer):
                try:
                    closer()
                except BaseException:
                    pass
            row = {"iq_a": iq, "if_a": IF_A, **parts,
                   "mesh": pos.get("mesh_elements")}
            rows.append(row)
            print(json.dumps(row))
    finally:
        closer = getattr(handle, "closefemm", None)
        if callable(closer):
            try:
                closer()
            except BaseException:
                pass
    path = os.path.join(OUT, "even_sweep.json")
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(rows, stream, indent=2)
        stream.write("\n")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
