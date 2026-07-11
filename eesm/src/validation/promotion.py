"""Stable all-required-gates-first EESM candidate promotion."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any, Mapping, Sequence


RANKING_FIELDS = (
    "scheduler_loss_regret_w",
    "torque_rmse_nm",
    "flux_rmse_wb",
    "training_runtime_s",
)


def _candidate_id(run: Mapping[str, Any]) -> str:
    if run.get("candidate_id"):
        return str(run["candidate_id"])
    fields = [run.get("strategy"), run.get("budget"), run.get("family")]
    populated = [str(value) for value in fields if value is not None]
    if not populated:
        raise ValueError("candidate is missing identity")
    return "|".join(populated)


def _ranking_score(run: Mapping[str, Any]) -> tuple[float, float, float, float, str]:
    values: list[float] = []
    for field in RANKING_FIELDS:
        value = run.get(field)
        if (
            not isinstance(value, Real)
            or isinstance(value, bool)
            or not math.isfinite(float(value))
        ):
            raise ValueError(f"candidate missing finite {field}")
        values.append(float(value))
    family = str(run.get("family", ""))
    if not family:
        raise ValueError("candidate missing family")
    return (*values, family)


def promote_candidate(
    run_summaries: Sequence[Mapping[str, Any]],
    gate_results: Mapping[str, Mapping[str, Any]],
    policy: str,
) -> dict[str, Any]:
    """Filter to all-gates-pass runs, then apply the frozen stable ranking."""
    if policy != "all_required_then_loss":
        raise ValueError(f"unknown promotion policy: {policy}")

    candidates: list[tuple[tuple[float, float, float, float, str], str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    rejected: list[str] = []
    family_counts: dict[str, int] = {}
    for run in run_summaries:
        family = str(run.get("family", ""))
        family_counts[family] = family_counts.get(family, 0) + 1
    for run in run_summaries:
        candidate_id = _candidate_id(run)
        if candidate_id in seen:
            raise ValueError(f"duplicate candidate identity: {candidate_id}")
        seen.add(candidate_id)
        result = gate_results.get(candidate_id)
        if result is None and run.get("family") is not None:
            family = str(run["family"])
            family_result = gate_results.get(family)
            if family_result is not None and family_counts[family] > 1:
                raise ValueError(
                    f"candidate-specific gate result required for {candidate_id}"
                )
            result = family_result
        if not isinstance(result, Mapping) or not bool(
            result.get("all_required_pass", False)
        ):
            rejected.append(candidate_id)
            continue
        candidates.append((_ranking_score(run), candidate_id, run))

    if not candidates:
        return {
            "status": "no_promotion",
            "family": None,
            "candidate_id": None,
            "rejected_candidates": rejected,
            "reason": "no candidate passed all required gates",
        }

    score, candidate_id, selected = min(candidates, key=lambda item: item[0])
    return {
        "status": "promoted",
        "candidate_id": candidate_id,
        "family": str(selected["family"]),
        "strategy": selected.get("strategy"),
        "budget": selected.get("budget"),
        "ranking": dict(zip((*RANKING_FIELDS, "family"), score)),
        "rejected_candidates": rejected,
    }
