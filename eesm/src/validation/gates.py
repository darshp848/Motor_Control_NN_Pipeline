"""Deterministic evaluation of frozen EESM promotion gates."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any, Mapping


REQUIRED_GATES = (
    "data_qa",
    "interior",
    "boundary",
    "saturation",
    "field_weakening",
    "torque",
    "voltage",
    "feasibility",
)


def _threshold_values(frozen_thresholds: Mapping[str, Any]) -> Mapping[str, Any]:
    if "thresholds" in frozen_thresholds:
        if frozen_thresholds.get("status") != "frozen":
            raise ValueError("thresholds not frozen")
        values = frozen_thresholds["thresholds"]
    else:
        values = frozen_thresholds
    if not isinstance(values, Mapping):
        raise ValueError("thresholds not frozen")
    if any(gate not in values or values[gate] is None for gate in REQUIRED_GATES):
        raise ValueError("thresholds not frozen")
    return values


def evaluate_gates(
    metrics: Mapping[str, Any], frozen_thresholds: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare every required lower-is-better metric with a frozen threshold."""
    thresholds = _threshold_values(frozen_thresholds)
    gate_values = metrics.get("gate_values", metrics)
    if not isinstance(gate_values, Mapping):
        raise ValueError("metrics must provide gate_values")

    results: dict[str, dict[str, Any]] = {}
    for gate in REQUIRED_GATES:
        threshold = thresholds[gate]
        if (
            not isinstance(threshold, Real)
            or isinstance(threshold, bool)
            or not math.isfinite(float(threshold))
            or float(threshold) < 0.0
        ):
            raise ValueError(f"invalid frozen threshold for {gate}")
        raw_value = gate_values.get(gate, float("nan"))
        available = (
            isinstance(raw_value, Real)
            and not isinstance(raw_value, bool)
            and math.isfinite(float(raw_value))
        )
        value = float(raw_value) if available else float("nan")
        passed = bool(available and value <= float(threshold))
        results[gate] = {
            "value": value,
            "threshold": float(threshold),
            "available": available,
            "passed": passed,
            "reason": "within_threshold" if passed else (
                "metric_unavailable" if not available else "threshold_exceeded"
            ),
        }

    all_required_pass = all(result["passed"] for result in results.values())
    return {
        "required": list(REQUIRED_GATES),
        "gates": results,
        "all_required_pass": all_required_pass,
        "status": "passed" if all_required_pass else "failed",
    }
