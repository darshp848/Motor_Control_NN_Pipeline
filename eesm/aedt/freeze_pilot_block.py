"""Freeze the PILOT_EXECUTION_PLAN.md Phase 3 pilot block (offline, CPython).

Writes the canonical 8-point pilot CSV and its SHA-256 to
out/eesm/pilot_20260721/, using the SAME canonical_point_id as the offline
pipeline (eesm/src/data/experiment_points.py) so the IronPython exporter
(eesm/aedt/export_eesm_points.py) agrees on every point identity. The
exporter re-reads, re-hashes, and verifies identity on the live design; a
drift between this freeze and the exporter's IronPython port of
canonical_point_id would surface there as 'Point identity mismatch'.

Point design (PILOT_EXECUTION_PLAN.md Phase 3.1)
-------------------------------------------------
All currents are TERMINAL amps (the r2 winding contract: four parallel
stator branches -> 36 series turns/phase -> commanded current is the
terminal current; AEDT drives each branch with I/4). Nothing approaches
the legacy 200 A-terminal excursions (NOTES 4). Positions:

  1. field_only_3a    (0,    0,   If=3)  field-only at If != 2 -> confirms
                                         the 330.01 deg d-axis (NOTES 2)
  2. field_only_5a    (0,    0,   If=5)  second field-only -> d-axis
                                         confirmation 4.4 AND d lam_d/dIf
                                         > 0 at a second If (4.6)
  3. pure_d_neg       (-30, 0,   If=2)  Ld probe
  4. pure_q_pos       (0,   30,  If=2)  Lq probe
  5. q_neg            (0,  -30,  If=2)  negative-q symmetry check
  6. combined_modest  (-20, 25,  If=3)  modest combined load
  7. saturation_nbrhd (-45, 35,  If=5)  saturation neighbourhood
  8. rated_ish        (-30, 45,  If=4)  rated-ish operating point

Two field-only points at distinct If let Phase 4.4 confirm the d-axis
angle from a SECOND point and Phase 4.6 read d(lambda_d)/d(If) > 0 from a
clean same-frame pair, not just from the OLS batch gate.

This script writes files only. It does NOT solve, qualify, or promote. The
old Task 9 dataset stays quarantined.
"""

from __future__ import annotations

import csv
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
SRC_DIR = os.path.join(REPO_ROOT, "eesm", "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from data.experiment_points import canonical_point_id  # noqa: E402

PILOT_ID = "eesm_pilot_20260721"
FREEZE_SOURCE_TAG = "eesm_pilot_freeze_20260721"

OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "pilot_20260721")
POINTS_CSV = os.path.join(OUT_DIR, "frozen_points.csv")
POINTS_SHA256 = os.path.join(OUT_DIR, "frozen_points.sha256")

# Must match FROZEN_POINT_FIELDS in eesm/aedt/export_eesm_points.py exactly.
FROZEN_POINT_FIELDS = [
    "point_name", "point_id", "role", "region",
    "id_a", "iq_a", "if_a", "source", "provenance_note",
]


# Each tuple: (point_name, id_a, iq_a, if_a, role, region, provenance_note).
_PILOT_POINT_SPEC = [
    ("field_only_3a", 0.0, 0.0, 3.0, "reference", "interior",
     "field-only at If=3A (different from the diagnostic's 2A); confirms "
     "D_AXIS_ELECTRICAL_DEG=330.01 (NOTES 2/Phase 4.4) and contributes to "
     "d(lambda_d)/d(If) > 0 (Phase 4.6)."),
    ("field_only_5a", 0.0, 0.0, 5.0, "reference", "interior",
     "second field-only point at a distinct If; Phase 4.4 second-point "
     "d-axis check and Phase 4.6 clean same-frame d(lambda_d)/d(If)."),
    ("pure_d_neg", -30.0, 0.0, 2.0, "reference", "interior",
     "pure negative-d at modest terminal amps; Ld probe (Phase 4.5)."),
    ("pure_q_pos", 0.0, 30.0, 2.0, "reference", "interior",
     "pure positive-q at modest terminal amps; Lq probe (Phase 4.5). The "
     "0.0797 q-probe caveat from the diagnostic was plausibly mesh-limited; "
     "the denser pilot mesh decides."),
    ("q_neg", 0.0, -30.0, 2.0, "reference", "interior",
     "negative-q symmetry probe; closes the q-axis sign convention."),
    ("combined_modest", -20.0, 25.0, 3.0, "reference", "interior",
     "modest combined load well inside the exporter domain; cross-checks "
     "the dq identity under simultaneous excitation."),
    ("saturation_nbrhd", -45.0, 35.0, 5.0, "reference", "saturation",
     "saturation-neighbourhood point; probes where Ld/Lq begin to droop. "
     "Torque-closure target is < 10% at UNSATURATED points, so this row is "
     "expected to be the loosest and is reported, not tuned."),
    ("rated_ish", -30.0, 45.0, 4.0, "reference", "boundary",
     "rated-ish operating point near the manifest's 80 Nm rated torque; "
     "the closest point to a real controller operating condition."),
]


def build_pilot_points():
    """Return the eight pilot point rows as dicts with FROZEN_POINT_FIELDS.

    point_id uses the pipeline-wide canonical_point_id so every consumer
    (this freeze, the offline schema tests, the IronPython exporter)
    agrees on identity. Currents are formatted with nine decimals in the
    CSV so float(str) round-trips exactly under the exporter's identity
    re-check.
    """
    rows = []
    for name, id_a, iq_a, if_a, role, region, note in _PILOT_POINT_SPEC:
        rows.append({
            "point_name": name,
            "point_id": canonical_point_id(id_a, iq_a, if_a),
            "role": role,
            "region": region,
            "id_a": "%.9f" % id_a,
            "iq_a": "%.9f" % iq_a,
            "if_a": "%.9f" % if_a,
            "source": FREEZE_SOURCE_TAG,
            "provenance_note": note,
        })
    return rows


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def main():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    rows = build_pilot_points()

    # Drift guard: column order and point identity must match what the
    # IronPython exporter will re-read.
    if [r["point_name"] for r in rows] != [
            spec[0] for spec in _PILOT_POINT_SPEC]:
        raise RuntimeError("internal: row ordering drift")
    seen = set()
    for row in rows:
        key = (row["point_name"], row["point_id"])
        if key in seen:
            raise RuntimeError("duplicate pilot point: " + row["point_name"])
        seen.add(key)

    with open(POINTS_CSV, "w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FROZEN_POINT_FIELDS,
                                lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    digest = _sha256_file(POINTS_CSV)
    with open(POINTS_SHA256, "w") as stream:
        stream.write(digest + "\n")

    print("Froze pilot block:")
    print("  csv    : " + POINTS_CSV)
    print("  sha256 : " + digest)
    print("  points : " + str(len(rows)))
    for row in rows:
        print("  %-18s %s  id=%s iq=%s if=%s" % (
            row["point_name"], row["point_id"],
            row["id_a"], row["iq_a"], row["if_a"]))


if __name__ == "__main__":
    main()