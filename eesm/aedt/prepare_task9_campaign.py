"""Freeze the deterministic 64-point Task 9 Maxwell baseline campaign."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_ROOT = REPO_ROOT / "out" / "eesm" / "task9_baseline"
POINTS_PATH = CAMPAIGN_ROOT / "frozen_points.csv"
FREEZE_PATH = CAMPAIGN_ROOT / "campaign_freeze.json"
PROGRESS_PATH = CAMPAIGN_ROOT / "raw" / "campaign_progress.csv"
CAMPAIGN_ID = "eesm_task9_real_baseline_20260715"
CAMPAIGN_BUDGET = 64
ROLE_COUNTS = {
    "train": 40,
    "selection": 12,
    "reference": 8,
    "scheduler_audit": 4,
}
ROLE_SEEDS = {
    "train": 20260710,
    "selection": 20260711,
    "reference": 20260712,
    "scheduler_audit": 2909,
}
DOMAIN = {
    "id_a": (-120.0, 0.0),
    "iq_a": (0.0, 120.0),
    "if_a": (0.0, 15.0),
}
FIELDS = (
    "PointName", "point_id", "role", "region", "Id [A]", "Iq [A]",
    "If [A]", "campaign_id", "seed", "sample_index",
)

# Reviewed anchors guarantee coverage without adapting to FEM results.
ANCHORS = {
    "train": [
        (-120.0, 0.0, 1.0, "boundary"),
        (-120.0, 120.0, 15.0, "boundary"),
        (0.0, 120.0, 7.5, "boundary"),
        (0.0, 0.0, 2.0, "boundary"),
        (-100.0, 30.0, 3.0, "field_weakening"),
        (-110.0, 80.0, 10.0, "field_weakening"),
        (-30.0, 110.0, 14.0, "saturation"),
        (-70.0, 100.0, 13.0, "saturation"),
    ],
    "selection": [
        (-120.0, 60.0, 8.0, "boundary"),
        (-60.0, 120.0, 8.0, "boundary"),
        (-105.0, 45.0, 6.0, "field_weakening"),
        (-35.0, 105.0, 13.0, "saturation"),
    ],
    "reference": [
        (0.0, 60.0, 8.0, "boundary"),
        (-100.0, 100.0, 5.0, "field_weakening"),
        (-20.0, 90.0, 15.0, "saturation"),
    ],
    "scheduler_audit": [
        (-90.0, 90.0, 12.0, "saturation"),
    ],
}


def _format_current(value: float) -> str:
    rounded = round(float(value), 9) or 0.0
    return f"{rounded:.9f}"


def _point_id(currents: tuple[float, float, float]) -> str:
    payload = "|".join(_format_current(value) for value in currents)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()[:16]


def _lhs(n: int, seed: int) -> list[tuple[float, float, float]]:
    rng = random.Random(seed)
    axes: list[list[float]] = []
    for low, high in DOMAIN.values():
        values = [low + ((index + rng.random()) / n) * (high - low) for index in range(n)]
        rng.shuffle(values)
        axes.append(values)
    return [tuple(round(axes[axis][index], 6) for axis in range(3)) for index in range(n)]


def _region(currents: tuple[float, float, float]) -> str:
    id_a, iq_a, if_a = currents
    if id_a <= -96.0:
        return "field_weakening"
    if if_a >= 12.0 or (abs(id_a) + iq_a) >= 180.0:
        return "saturation"
    return "interior"


def build_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for role in ("train", "selection", "reference", "scheduler_audit"):
        anchors = ANCHORS[role]
        generated = _lhs(ROLE_COUNTS[role] - len(anchors), ROLE_SEEDS[role])
        candidates = [(a, b, c, region) for a, b, c, region in anchors]
        candidates.extend((*currents, _region(currents)) for currents in generated)
        for index, (id_a, iq_a, if_a, region) in enumerate(candidates):
            currents = (float(id_a), float(iq_a), float(if_a))
            point_id = _point_id(currents)
            rows.append({
                "PointName": point_id,
                "point_id": point_id,
                "role": role,
                "region": region,
                "Id [A]": _format_current(currents[0]),
                "Iq [A]": _format_current(currents[1]),
                "If [A]": _format_current(currents[2]),
                "campaign_id": CAMPAIGN_ID,
                "seed": ROLE_SEEDS[role],
                "sample_index": index,
            })
    return rows


def _render_points(rows: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("ascii")


def freeze_campaign() -> dict[str, object]:
    rows = build_rows()
    if len(rows) != CAMPAIGN_BUDGET:
        raise ValueError("Task 9 campaign budget mismatch")
    ids = [str(row["point_id"]) for row in rows]
    currents = [(row["Id [A]"], row["Iq [A]"], row["If [A]"]) for row in rows]
    if len(set(ids)) != len(ids) or len(set(currents)) != len(currents):
        raise ValueError("Task 9 campaign contains duplicate points")
    if any(tuple(float(value) for value in current) == (0.0, 0.0, 0.0) for current in currents):
        raise ValueError("source-free origin must not be requested from AEDT")
    if Counter(str(row["role"]) for row in rows) != Counter(ROLE_COUNTS):
        raise ValueError("Task 9 role budget mismatch")

    points_bytes = _render_points(rows)
    points_sha256 = hashlib.sha256(points_bytes).hexdigest()
    freeze = {
        "campaign_id": CAMPAIGN_ID,
        "campaign_budget": CAMPAIGN_BUDGET,
        "role_counts": ROLE_COUNTS,
        "role_seeds": ROLE_SEEDS,
        "domain": DOMAIN,
        "source_free_origin_policy": "analytic_invariant_not_sent_to_aedt",
        "sampling_revision_policy": "frozen_before_fem_no_result_driven_revision",
        "points_path": POINTS_PATH.relative_to(REPO_ROOT).as_posix(),
        "points_sha256": points_sha256,
    }
    if POINTS_PATH.exists() or FREEZE_PATH.exists():
        if not (POINTS_PATH.is_file() and FREEZE_PATH.is_file()):
            raise FileExistsError("Task 9 freeze is incomplete; refusing to overwrite it")
        existing_freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
        existing_sha256 = hashlib.sha256(POINTS_PATH.read_bytes()).hexdigest()
        if existing_sha256 != points_sha256 or existing_freeze.get("points_sha256") != points_sha256:
            raise FileExistsError("Task 9 freeze differs from the reviewed campaign; refusing overwrite")
        return existing_freeze
    if PROGRESS_PATH.exists() and PROGRESS_PATH.stat().st_size:
        raise FileExistsError("Task 9 progress exists without a freeze; refusing regeneration")

    CAMPAIGN_ROOT.mkdir(parents=True, exist_ok=True)
    POINTS_PATH.write_bytes(points_bytes)
    FREEZE_PATH.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return freeze


if __name__ == "__main__":
    print(json.dumps(freeze_campaign(), indent=2, sort_keys=True))
