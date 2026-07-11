"""Controller-relevant EESM flux, torque, voltage, and scheduler metrics."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any, Mapping, Sequence

import numpy as np

from scheduler.copper_loss_scheduler import (
    copper_loss,
    electromagnetic_torque_eesm,
    rpm_mech_to_we,
    stator_voltage_eesm,
)


REGIONS = (
    "interior",
    "boundary",
    "saturation",
    "field_weakening",
    "unsupported",
)


def _has_column(points: object, name: str) -> bool:
    if isinstance(points, Mapping):
        return name in points
    columns = getattr(points, "columns", ())
    return name in columns


def _column(points: object, name: str, *, required: bool = True) -> np.ndarray | None:
    if not _has_column(points, name):
        if required:
            raise ValueError(f"points missing required column: {name}")
        return None
    try:
        values = points[name]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"points missing required column: {name}") from exc
    return np.asarray(values)


def _flux_array(flux: object, name: str) -> np.ndarray:
    if isinstance(flux, Mapping) or hasattr(flux, "columns"):
        if not _has_column(flux, "lambda_d_wb") or not _has_column(
            flux, "lambda_q_wb"
        ):
            raise ValueError(f"{name} must contain lambda_d_wb and lambda_q_wb")
        values = np.column_stack(
            [
                _column(flux, "lambda_d_wb"),
                _column(flux, "lambda_q_wb"),
            ]
        )
    else:
        values = np.asarray(flux)
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 2:
        raise ValueError(f"{name} must have shape (n, 2)")
    return result


def _machine_number(machine: Mapping[str, Any], name: str) -> float:
    value = machine.get(name)
    if (
        not isinstance(value, Real)
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"machine missing finite {name}")
    return float(value)


def _error_stats(truth: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    n = int(truth.size)
    if n == 0:
        return {
            "mae": float("nan"),
            "rmse": float("nan"),
            "max_abs": float("nan"),
            "n": 0,
        }
    error = np.asarray(predicted - truth, dtype=np.float64)
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "max_abs": float(np.max(np.abs(error))),
        "n": n,
    }


def _speed_key(rpm: float) -> str:
    return str(int(rpm)) if float(rpm).is_integer() else f"{rpm:.17g}"


def _boolean_column(points: object, name: str) -> np.ndarray | None:
    raw = _column(points, name, required=False)
    if raw is None:
        return None
    flat = np.asarray(raw, dtype=object).ravel()
    if not all(isinstance(value, (bool, np.bool_)) for value in flat):
        raise ValueError(f"{name} must contain booleans")
    return flat.astype(bool)


def _scheduler_losses(
    points: object, n: int, rs_ohm: float, rf_ohm: float
) -> tuple[np.ndarray | None, np.ndarray | None]:
    current_columns = (
        "truth_id_a",
        "truth_iq_a",
        "truth_if_a",
        "predicted_id_a",
        "predicted_iq_a",
        "predicted_if_a",
    )
    present = [_has_column(points, name) for name in current_columns]
    supplied_losses = _has_column(points, "truth_p_cu_w") or _has_column(
        points, "predicted_p_cu_w"
    )
    if not any(present):
        if supplied_losses:
            raise ValueError(
                "copper-loss regret requires scheduler current columns"
            )
        return None, None
    if not all(present):
        raise ValueError("all truth and predicted scheduler current columns are required")

    currents = {
        name: np.asarray(_column(points, name), dtype=np.float64).ravel()
        for name in current_columns
    }
    if any(values.size != n for values in currents.values()):
        raise ValueError("scheduler current columns must be row aligned")
    if any(np.isinf(values).any() for values in currents.values()):
        raise ValueError("scheduler current columns cannot contain infinity")

    truth_finite = np.column_stack(
        [currents[name] for name in current_columns[:3]]
    )
    predicted_finite = np.column_stack(
        [currents[name] for name in current_columns[3:]]
    )
    for label, values in (
        ("truth", truth_finite),
        ("predicted", predicted_finite),
    ):
        count = np.sum(np.isfinite(values), axis=1)
        if np.any((count != 0) & (count != 3)):
            raise ValueError(
                f"{label} scheduler currents must be all finite or all missing"
            )

    truth_loss = copper_loss(
        currents["truth_id_a"],
        currents["truth_iq_a"],
        currents["truth_if_a"],
        rs_ohm,
        rf_ohm,
    )
    predicted_loss = copper_loss(
        currents["predicted_id_a"],
        currents["predicted_iq_a"],
        currents["predicted_if_a"],
        rs_ohm,
        rf_ohm,
    )

    if supplied_losses:
        if not (
            _has_column(points, "truth_p_cu_w")
            and _has_column(points, "predicted_p_cu_w")
        ):
            raise ValueError(
                "truth_p_cu_w and predicted_p_cu_w must be supplied together"
            )
        for name, computed in (
            ("truth_p_cu_w", truth_loss),
            ("predicted_p_cu_w", predicted_loss),
        ):
            reported = np.asarray(_column(points, name), dtype=np.float64).ravel()
            if reported.size != n or np.isinf(reported).any():
                raise ValueError("reported copper losses must be row aligned and finite")
            comparable = np.isfinite(computed)
            if not np.array_equal(np.isfinite(reported), comparable) or not np.allclose(
                reported[comparable], computed[comparable], rtol=1e-10, atol=1e-10
            ):
                raise ValueError(f"{name} does not match the frozen copper-loss formula")
    return truth_loss, predicted_loss


def _data_qa(points: object, n: int) -> dict[str, Any]:
    passed = _boolean_column(points, "data_qa_passed")
    if passed is None:
        return {
            "n": 0,
            "failed_checks": 0,
            "failure_rate": float("nan"),
            "available": False,
        }
    if passed.size != n:
        raise ValueError("data_qa_passed must be row aligned")
    failed = int(np.sum(~passed))
    return {
        "n": n,
        "failed_checks": failed,
        "failure_rate": float(failed / n),
        "available": True,
    }


def _feasibility_confusion(
    truth: np.ndarray | None,
    predicted: np.ndarray | None,
    mask: np.ndarray,
) -> dict[str, Any]:
    if truth is None and predicted is None:
        return {
            "labels": ["infeasible", "feasible"],
            "matrix": [[0, 0], [0, 0]],
            "n": 0,
            "accuracy": float("nan"),
            "error_rate": float("nan"),
        }
    if truth is None or predicted is None:
        raise ValueError(
            "truth_feasible and predicted_feasible must be supplied together"
        )
    truth_subset = truth[mask]
    predicted_subset = predicted[mask]
    tn = int(np.sum(~truth_subset & ~predicted_subset))
    fp = int(np.sum(~truth_subset & predicted_subset))
    fn = int(np.sum(truth_subset & ~predicted_subset))
    tp = int(np.sum(truth_subset & predicted_subset))
    n = int(truth_subset.size)
    correct = tn + tp
    return {
        "labels": ["infeasible", "feasible"],
        "matrix": [[tn, fp], [fn, tp]],
        "n": n,
        "accuracy": float(correct / n) if n else float("nan"),
        "error_rate": float(1.0 - correct / n) if n else float("nan"),
    }


def _regret_stats(
    truth_p_cu: np.ndarray | None,
    predicted_p_cu: np.ndarray | None,
    mask: np.ndarray,
) -> dict[str, Any]:
    if truth_p_cu is None and predicted_p_cu is None:
        return {
            "mean": float("nan"),
            "max": float("nan"),
            "max_abs": float("nan"),
            "n": 0,
        }
    if truth_p_cu is None or predicted_p_cu is None:
        raise ValueError(
            "truth_p_cu_w and predicted_p_cu_w must be supplied together"
        )
    finite = mask & np.isfinite(truth_p_cu) & np.isfinite(predicted_p_cu)
    regret = predicted_p_cu[finite] - truth_p_cu[finite]
    if regret.size == 0:
        return {
            "mean": float("nan"),
            "max": float("nan"),
            "max_abs": float("nan"),
            "n": 0,
        }
    return {
        "mean": float(np.mean(regret)),
        "max": float(np.max(regret)),
        "max_abs": float(np.max(np.abs(regret))),
        "n": int(regret.size),
    }


def _region_block(
    mask: np.ndarray,
    truth_flux: np.ndarray,
    predicted_flux: np.ndarray,
    truth_torque: np.ndarray,
    predicted_torque: np.ndarray,
    truth_voltage: Mapping[str, np.ndarray],
    predicted_voltage: Mapping[str, np.ndarray],
    truth_feasible: np.ndarray | None,
    predicted_feasible: np.ndarray | None,
    truth_p_cu: np.ndarray | None,
    predicted_p_cu: np.ndarray | None,
) -> dict[str, Any]:
    return {
        "n": int(np.sum(mask)),
        "flux": {
            "lambda_d_wb": _error_stats(
                truth_flux[mask, 0], predicted_flux[mask, 0]
            ),
            "lambda_q_wb": _error_stats(
                truth_flux[mask, 1], predicted_flux[mask, 1]
            ),
        },
        "torque_nm": _error_stats(
            truth_torque[mask], predicted_torque[mask]
        ),
        "voltage_magnitude_v": {
            speed: _error_stats(values[mask], predicted_voltage[speed][mask])
            for speed, values in truth_voltage.items()
        },
        "feasibility_confusion": _feasibility_confusion(
            truth_feasible, predicted_feasible, mask
        ),
        "copper_loss_regret_w": _regret_stats(
            truth_p_cu, predicted_p_cu, mask
        ),
    }


def evaluate_controller_metrics(
    points: object,
    truth_flux: object,
    predicted_flux: object,
    machine: Mapping[str, Any],
    speeds_rpm: Sequence[float],
) -> dict[str, Any]:
    """Evaluate row-aligned controller metrics without merging unsupported rows."""
    id_a = np.asarray(_column(points, "id_a"), dtype=np.float64).ravel()
    iq_a = np.asarray(_column(points, "iq_a"), dtype=np.float64).ravel()
    if_a = np.asarray(_column(points, "if_a"), dtype=np.float64).ravel()
    regions = np.asarray(_column(points, "region"), dtype=object).ravel()
    n = int(id_a.size)
    if not (iq_a.size == if_a.size == regions.size == n):
        raise ValueError("point columns must be row aligned")
    actual = _flux_array(truth_flux, "truth_flux")
    predicted = _flux_array(predicted_flux, "predicted_flux")
    if actual.shape[0] != n or predicted.shape[0] != n:
        raise ValueError("points and flux arrays must be row aligned")
    if n == 0 or not (
        np.isfinite(id_a).all()
        and np.isfinite(iq_a).all()
        and np.isfinite(if_a).all()
        and np.isfinite(actual).all()
        and np.isfinite(predicted).all()
    ):
        raise ValueError("controller metric inputs must be non-empty and finite")
    unknown_regions = sorted(set(str(value) for value in regions) - set(REGIONS))
    if unknown_regions:
        raise ValueError(f"unknown controller regions: {unknown_regions}")

    pole_pairs = int(_machine_number(machine, "pole_pairs"))
    if pole_pairs <= 0:
        raise ValueError("pole_pairs must be positive")
    rs_ohm = _machine_number(machine, "rs_ohm")
    rf_ohm = _machine_number(machine, "rf_ohm")
    speed_values = np.asarray(list(speeds_rpm), dtype=np.float64).ravel()
    if speed_values.size == 0 or not np.isfinite(speed_values).all() or np.any(
        speed_values < 0.0
    ):
        raise ValueError("speeds_rpm must contain finite non-negative speeds")
    if len(set(float(value) for value in speed_values)) != speed_values.size:
        raise ValueError("speeds_rpm must not contain duplicates")

    truth_torque = electromagnetic_torque_eesm(
        id_a, iq_a, actual[:, 0], actual[:, 1], pole_pairs
    )
    predicted_torque = electromagnetic_torque_eesm(
        id_a, iq_a, predicted[:, 0], predicted[:, 1], pole_pairs
    )
    truth_voltage: dict[str, np.ndarray] = {}
    predicted_voltage: dict[str, np.ndarray] = {}
    for rpm in speed_values:
        key = _speed_key(float(rpm))
        omega_e = rpm_mech_to_we(float(rpm), pole_pairs)
        truth_voltage[key] = stator_voltage_eesm(
            id_a, iq_a, actual[:, 0], actual[:, 1], omega_e, rs_ohm
        )[2]
        predicted_voltage[key] = stator_voltage_eesm(
            id_a,
            iq_a,
            predicted[:, 0],
            predicted[:, 1],
            omega_e,
            rs_ohm,
        )[2]

    truth_feasible = _boolean_column(points, "truth_feasible")
    predicted_feasible = _boolean_column(points, "predicted_feasible")
    truth_p_cu, predicted_p_cu = _scheduler_losses(
        points, n, rs_ohm, rf_ohm
    )
    data_qa = _data_qa(points, n)
    for optional in (
        truth_feasible,
        predicted_feasible,
        truth_p_cu,
        predicted_p_cu,
    ):
        if optional is not None and optional.size != n:
            raise ValueError("optional scheduler metrics must be row aligned")

    all_rows = np.ones(n, dtype=bool)
    overall = _region_block(
        all_rows,
        actual,
        predicted,
        truth_torque,
        predicted_torque,
        truth_voltage,
        predicted_voltage,
        truth_feasible,
        predicted_feasible,
        truth_p_cu,
        predicted_p_cu,
    )
    by_region = {
        region: _region_block(
            regions == region,
            actual,
            predicted,
            truth_torque,
            predicted_torque,
            truth_voltage,
            predicted_voltage,
            truth_feasible,
            predicted_feasible,
            truth_p_cu,
            predicted_p_cu,
        )
        for region in REGIONS
    }

    voltage_rmse = [
        entry["rmse"]
        for entry in overall["voltage_magnitude_v"].values()
        if math.isfinite(entry["rmse"])
    ]
    gate_values = {
        "data_qa": data_qa["failure_rate"],
        **{
            region: max(
                by_region[region]["flux"]["lambda_d_wb"]["rmse"],
                by_region[region]["flux"]["lambda_q_wb"]["rmse"],
            )
            if by_region[region]["n"]
            else float("nan")
            for region in REGIONS
            if region != "unsupported"
        },
        "torque": overall["torque_nm"]["rmse"],
        "voltage": max(voltage_rmse) if voltage_rmse else float("nan"),
        "feasibility": overall["feasibility_confusion"]["error_rate"],
    }
    return {
        "n": n,
        "speeds_rpm": [float(value) for value in speed_values],
        "overall": overall,
        "by_region": by_region,
        "feasibility_confusion": overall["feasibility_confusion"],
        "copper_loss_regret_w": overall["copper_loss_regret_w"],
        "data_qa": data_qa,
        "gate_values": gate_values,
    }
