"""Freeze the manifest equal-budget point identities for later FEMM solves.

This is not an expansion of Task 9. The Task 9 freeze stays write-once at
`out/eesm/task9_baseline/`. Manifest budgets 64/128/256 are training sizes
for tensor_grid, random, and latin_hypercube. Selection and scheduler_audit
are one shared reserved set each, sized to max(budget)=256.

The source-free origin (0, 0, 0) A is recorded as an analytic identity and
is never written into a FEMM-solvable points file.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

_EESM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_EESM_ROOT, "src")
_REPO_ROOT = os.path.dirname(_EESM_ROOT)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from data.experiment_points import canonical_point_id  # noqa: E402
from experiments import equal_budget  # noqa: E402

from .campaign import FROZEN_POINT_FIELDS  # noqa: E402

MANIFEST_PATH = os.path.join(
    _EESM_ROOT, "configs", "eesm_experiment_manifest.json"
)
TASK9_ROOT = os.path.join(_REPO_ROOT, "out", "eesm", "task9_baseline")
DEFAULT_FREEZE_ROOT = os.path.join(
    _REPO_ROOT, "out", "eesm", "femm_equal_budget_points_20260813"
)

ORIGIN = (0.0, 0.0, 0.0)
FEMM_POINT_FIELDS: Sequence[str] = FROZEN_POINT_FIELDS
ROLE_ORDER = ("train", "selection", "scheduler_audit")


class BudgetPointsRefusal(RuntimeError):
    """A freeze invariant failed. Nothing was written."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def is_origin(id_a: float, iq_a: float, if_a: float,
              atol: float = 1.0e-12) -> bool:
    return (
        abs(float(id_a) - ORIGIN[0]) <= atol
        and abs(float(iq_a) - ORIGIN[1]) <= atol
        and abs(float(if_a) - ORIGIN[2]) <= atol
    )


def classify_region(
    id_a: float,
    iq_a: float,
    if_a: float,
    domain: Mapping[str, Tuple[float, float]],
) -> str:
    """Label a current tuple for campaign QA.

    Field-weakening / saturation cutoffs match Task 9's generated-point
    rule. A remaining domain-face sample is `boundary`; otherwise
    `interior`. Explicit Task 9 anchors are not reused.
    """
    id_a = float(id_a)
    iq_a = float(iq_a)
    if_a = float(if_a)
    if id_a <= -96.0:
        return "field_weakening"
    if if_a >= 12.0 or (abs(id_a) + iq_a) >= 180.0:
        return "saturation"
    id_bounds = domain["id_a"]
    iq_bounds = domain["iq_a"]
    if_bounds = domain["if_a"]
    on_face = (
        abs(id_a - id_bounds[0]) <= 1.0e-9
        or abs(id_a - id_bounds[1]) <= 1.0e-9
        or abs(iq_a - iq_bounds[0]) <= 1.0e-9
        or abs(iq_a - iq_bounds[1]) <= 1.0e-9
        or abs(if_a - if_bounds[0]) <= 1.0e-9
        or abs(if_a - if_bounds[1]) <= 1.0e-9
    )
    return "boundary" if on_face else "interior"


def _domain_bounds(domain_obj: Any) -> Dict[str, Tuple[float, float]]:
    return {
        "id_a": (float(domain_obj.id_min_a), float(domain_obj.id_max_a)),
        "iq_a": (float(domain_obj.iq_min_a), float(domain_obj.iq_max_a)),
        "if_a": (float(domain_obj.if_min_a), float(domain_obj.if_max_a)),
    }


def _row_from_sample(
    point_id: str,
    role: str,
    id_a: float,
    iq_a: float,
    if_a: float,
    domain: Mapping[str, Tuple[float, float]],
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "point_name": point_id,
        "point_id": point_id,
        "role": role,
        "region": classify_region(id_a, iq_a, if_a, domain),
        "id_a": float(id_a),
        "iq_a": float(iq_a),
        "if_a": float(if_a),
    }
    if extra:
        row.update(extra)
    return row


def _samples_to_rows(
    samples: Mapping[str, Any],
    role: str,
    domain: Mapping[str, Tuple[float, float]],
    extra: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    count = len(samples["point_id"])
    for index in range(count):
        point_id = str(samples["point_id"][index])
        id_a = float(samples["id_a"][index])
        iq_a = float(samples["iq_a"][index])
        if_a = float(samples["if_a"][index])
        expected = canonical_point_id(id_a, iq_a, if_a)
        if point_id != expected:
            raise BudgetPointsRefusal(
                "Refusing freeze: sampler point_id %s != canonical %s"
                % (point_id, expected)
            )
        payload = dict(extra or {})
        payload["sample_index"] = index
        rows.append(
            _row_from_sample(point_id, role, id_a, iq_a, if_a, domain, payload)
        )
    return rows


def build_equal_budget_identities(
    manifest: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build the executable 64/128/256 identity catalog. Writes nothing."""
    strategies, budgets, _families, seeds = equal_budget._validate_manifest(
        manifest
    )
    domain_obj = equal_budget._domain_from_manifest(manifest)
    domain = _domain_bounds(domain_obj)
    role_budget = max(budgets)

    selection_seed = equal_budget._derived_seed(
        seeds["split"], "selection", role_budget
    )
    selection_samples = equal_budget.latin_hypercube_samples(
        domain_obj, n=role_budget, seed=selection_seed
    )
    audit_samples = equal_budget.latin_hypercube_samples(
        domain_obj, n=role_budget, seed=seeds["scheduler_audit"]
    )
    selection_rows = _samples_to_rows(
        selection_samples, "selection", domain,
        {"seed": selection_seed, "strategy": "latin_hypercube",
         "budget": role_budget},
    )
    audit_rows = _samples_to_rows(
        audit_samples, "scheduler_audit", domain,
        {"seed": seeds["scheduler_audit"], "strategy": "latin_hypercube",
         "budget": role_budget},
    )

    designs: Dict[str, Any] = {}
    train_rows: List[Dict[str, Any]] = []
    seen_train: Dict[str, Dict[str, Any]] = {}
    for strategy in strategies:
        for budget in budgets:
            sample_seed = equal_budget._derived_seed(
                seeds["split"], strategy, budget
            )
            samples = equal_budget._sample_training(
                strategy, domain_obj, budget, sample_seed
            )
            rows = _samples_to_rows(
                samples, "train", domain,
                {"seed": sample_seed, "strategy": strategy, "budget": budget},
            )
            key = "%s_%s" % (strategy, budget)
            designs[key] = {
                "strategy": strategy,
                "budget": budget,
                "seed": sample_seed,
                "point_ids": [row["point_id"] for row in rows],
                "n": len(rows),
            }
            for row in rows:
                point_id = row["point_id"]
                prior = seen_train.get(point_id)
                if prior is None:
                    seen_train[point_id] = row
                    train_rows.append(row)
                else:
                    if (
                        prior["id_a"] != row["id_a"]
                        or prior["iq_a"] != row["iq_a"]
                        or prior["if_a"] != row["if_a"]
                    ):
                        raise BudgetPointsRefusal(
                            "Refusing freeze: point_id %s maps to two currents"
                            % point_id
                        )

    reserved_ids = {
        row["point_id"] for row in selection_rows + audit_rows
    }
    train_ids = {row["point_id"] for row in train_rows}
    if train_ids & reserved_ids:
        raise BudgetPointsRefusal(
            "Refusing freeze: train overlaps a reserved role"
        )
    selection_ids = {row["point_id"] for row in selection_rows}
    audit_ids = {row["point_id"] for row in audit_rows}
    if selection_ids & audit_ids:
        raise BudgetPointsRefusal(
            "Refusing freeze: selection overlaps scheduler_audit"
        )

    origin_id = canonical_point_id(*ORIGIN)
    origin_in_train = origin_id in train_ids
    catalog_rows = train_rows + selection_rows + audit_rows
    femm_rows = [
        row for row in catalog_rows if not is_origin(row["id_a"], row["iq_a"], row["if_a"])
    ]
    femm_rows.sort(key=lambda row: (ROLE_ORDER.index(row["role"]), row["point_id"]))

    return {
        "strategies": list(strategies),
        "budgets": list(budgets),
        "seeds": dict(seeds),
        "domain": domain,
        "selection_seed": selection_seed,
        "designs": designs,
        "role_counts_including_origin": dict(Counter(row["role"] for row in catalog_rows)),
        "role_counts_femm": dict(Counter(row["role"] for row in femm_rows)),
        "n_identities": len(catalog_rows),
        "n_femm_solvable": len(femm_rows),
        "origin_point_id": origin_id,
        "origin_in_train": origin_in_train,
        "train_rows": train_rows,
        "selection_rows": selection_rows,
        "audit_rows": audit_rows,
        "femm_rows": femm_rows,
    }


def render_femm_points(rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=list(FEMM_POINT_FIELDS), extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "point_name": row["point_name"],
            "point_id": row["point_id"],
            "role": row["role"],
            "region": row["region"],
            "id_a": "%.9f" % float(row["id_a"]),
            "iq_a": "%.9f" % float(row["iq_a"]),
            "if_a": "%.9f" % float(row["if_a"]),
        })
    return stream.getvalue().encode("ascii")


def _write_json(path: str, payload: Mapping[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _guard_root(root: str) -> None:
    real_root = os.path.realpath(root)
    real_task9 = os.path.realpath(TASK9_ROOT)
    if real_root == real_task9 or real_root.startswith(real_task9 + os.sep):
        raise BudgetPointsRefusal(
            "Refusing freeze: destination is the Task 9 freeze (%s)." % TASK9_ROOT
        )


def freeze_equal_budget_points(
    root: str,
    manifest_path: str = MANIFEST_PATH,
) -> Dict[str, Any]:
    """Write a new identity freeze, or return the existing matching one."""
    _guard_root(root)
    with open(manifest_path, "rb") as stream:
        manifest_bytes = stream.read()
    manifest = json.loads(manifest_bytes)
    built = build_equal_budget_identities(manifest)

    points_bytes = render_femm_points(built["femm_rows"])
    points_sha256 = _sha256_bytes(points_bytes)
    freeze = {
        "campaign_id": "eesm_femm_equal_budget_points_20260813",
        "not_a_task9_expansion": True,
        "not_a_threshold_freeze": True,
        "source_free_origin_policy": "analytic_invariant_not_sent_to_femm",
        "sampling_revision_policy": "frozen_before_fem_no_result_driven_revision",
        "manifest_path": os.path.relpath(manifest_path, _REPO_ROOT).replace("\\", "/"),
        "manifest_sha256": _sha256_bytes(manifest_bytes),
        "strategies": built["strategies"],
        "budgets": built["budgets"],
        "seeds": built["seeds"],
        "selection_seed": built["selection_seed"],
        "domain": built["domain"],
        "designs": {
            key: {
                "strategy": value["strategy"],
                "budget": value["budget"],
                "seed": value["seed"],
                "n": value["n"],
                "point_ids_sha256": _sha256_bytes(
                    "\n".join(value["point_ids"]).encode("ascii")
                ),
            }
            for key, value in built["designs"].items()
        },
        "role_counts_including_origin": built["role_counts_including_origin"],
        "role_counts_femm": built["role_counts_femm"],
        "n_identities": built["n_identities"],
        "n_femm_solvable": built["n_femm_solvable"],
        "origin_point_id": built["origin_point_id"],
        "origin_in_train": built["origin_in_train"],
        "points_path": "frozen_points.csv",
        "points_sha256": points_sha256,
        "note": (
            "Identities for the executable equal-budget matrix. Task 9 "
            "40/12/8/4 remains a separate freeze. scheduler_audit is sealed."
        ),
    }

    points_path = os.path.join(root, "frozen_points.csv")
    freeze_path = os.path.join(root, "point_freeze.json")
    if os.path.exists(points_path) or os.path.exists(freeze_path):
        if not (os.path.isfile(points_path) and os.path.isfile(freeze_path)):
            raise BudgetPointsRefusal(
                "Refusing freeze: incomplete existing freeze in %s" % root
            )
        existing = json.loads(open(freeze_path, encoding="utf-8").read())
        existing_sha = sha256_file(points_path)
        if existing_sha != points_sha256 or existing.get("points_sha256") != points_sha256:
            raise BudgetPointsRefusal(
                "Refusing freeze: %s already holds a different identity freeze"
                % root
            )
        return existing

    os.makedirs(root, exist_ok=True)
    with open(points_path, "wb") as stream:
        stream.write(points_bytes)
    designs_dir = os.path.join(root, "designs")
    os.makedirs(designs_dir, exist_ok=True)
    for key, value in built["designs"].items():
        _write_json(os.path.join(designs_dir, key + ".json"), value)
    _write_json(os.path.join(designs_dir, "selection.json"), {
        "role": "selection",
        "seed": built["selection_seed"],
        "n": len(built["selection_rows"]),
        "point_ids": [row["point_id"] for row in built["selection_rows"]],
    })
    _write_json(os.path.join(designs_dir, "scheduler_audit.json"), {
        "role": "scheduler_audit",
        "seed": built["seeds"]["scheduler_audit"],
        "n": len(built["audit_rows"]),
        "point_ids": [row["point_id"] for row in built["audit_rows"]],
        "sealed": True,
    })
    _write_json(freeze_path, freeze)
    return freeze


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=DEFAULT_FREEZE_ROOT)
    parser.add_argument("--manifest", default=MANIFEST_PATH)
    ns = parser.parse_args(argv)
    try:
        freeze = freeze_equal_budget_points(ns.out, ns.manifest)
    except BudgetPointsRefusal as exc:
        print("REFUSED: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps({
        "root": os.path.abspath(ns.out),
        "points_sha256": freeze["points_sha256"],
        "n_identities": freeze["n_identities"],
        "n_femm_solvable": freeze["n_femm_solvable"],
        "role_counts_femm": freeze["role_counts_femm"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
