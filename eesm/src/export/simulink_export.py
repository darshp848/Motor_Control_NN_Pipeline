"""Fail-closed export of an EESM scheduler LUT for Simulink corroboration.

This is not electromagnetic truth and does not satisfy EESM-005 or EESM-006
until a prospective FEM audit hash is attached.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


EXPORT_COLUMNS = (
    "rpm_mech",
    "t_ref_nm",
    "id_ref_a",
    "iq_ref_a",
    "if_ref_a",
    "status",
    "torque_ok",
    "voltage_ok",
    "stator_current_ok",
    "field_current_ok",
    "domain_ok",
    "uncertainty_ok",
)

VALID_STATUS = {
    "feasible",
    "saturated_to_boundary",
    "infeasible",
}
SCHEDULABLE = {"feasible", "saturated_to_boundary"}
BOOL_COLUMNS = (
    "torque_ok",
    "voltage_ok",
    "stator_current_ok",
    "field_current_ok",
    "domain_ok",
    "uncertainty_ok",
)


class SimulinkExportRefusal(ValueError):
    """The LUT is not exportable. Nothing was written."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _as_bool(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise SimulinkExportRefusal(f"{name} must be a boolean")


def _finite_float(value: object, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SimulinkExportRefusal(f"{name} must be finite") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise SimulinkExportRefusal(f"{name} must be finite")
    return number


def validate_export_rows(
    rows: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Validate rows and return a normalized copy. Writes nothing."""
    if not rows:
        raise SimulinkExportRefusal("export has no rows")
    expected_hash = metadata.get("audit_model_sha256")
    supplied_hash = metadata.get("model_sha256")
    if not isinstance(expected_hash, str) or not expected_hash:
        raise SimulinkExportRefusal("metadata missing audit_model_sha256")
    if not isinstance(supplied_hash, str) or not supplied_hash:
        raise SimulinkExportRefusal("metadata missing model_sha256")
    if supplied_hash != expected_hash:
        raise SimulinkExportRefusal("audit-model hash mismatch")

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()
    for index, source in enumerate(rows):
        missing = [name for name in EXPORT_COLUMNS if name not in source]
        if missing:
            raise SimulinkExportRefusal(
                f"row {index} missing columns: {missing}"
            )
        status = str(source["status"])
        if status not in VALID_STATUS:
            raise SimulinkExportRefusal(f"row {index} has invalid status")
        rpm = _finite_float(source["rpm_mech"], "rpm_mech")
        torque = _finite_float(source["t_ref_nm"], "t_ref_nm")
        key = (round(rpm, 9), round(torque, 9))
        if key in seen:
            raise SimulinkExportRefusal(
                f"duplicate (rpm_mech, t_ref_nm) key: {key}"
            )
        seen.add(key)
        masks = {name: _as_bool(source[name], name) for name in BOOL_COLUMNS}
        if status in SCHEDULABLE:
            currents = {
                "id_ref_a": _finite_float(source["id_ref_a"], "id_ref_a"),
                "iq_ref_a": _finite_float(source["iq_ref_a"], "iq_ref_a"),
                "if_ref_a": _finite_float(source["if_ref_a"], "if_ref_a"),
            }
        else:
            if any(
                source[name] not in (None, "")
                and source[name] == source[name]
                for name in ("id_ref_a", "iq_ref_a", "if_ref_a")
                if isinstance(source[name], (int, float))
            ):
                # Infeasible rows may carry leftover currents; they must not
                # be treated as commands. Force empties in the export.
                pass
            currents = {
                "id_ref_a": 0.0,
                "iq_ref_a": 0.0,
                "if_ref_a": 0.0,
            }
            if any(masks[name] for name in (
                "torque_ok",
                "voltage_ok",
                "stator_current_ok",
                "field_current_ok",
                "domain_ok",
            )):
                raise SimulinkExportRefusal(
                    f"row {index}: infeasible status with a passing mask"
                )
        normalized.append(
            {
                "rpm_mech": rpm,
                "t_ref_nm": torque,
                "status": status,
                **currents,
                **masks,
            }
        )
    return normalized


def render_lut_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [",".join(EXPORT_COLUMNS)]
    for row in rows:
        values = []
        for name in EXPORT_COLUMNS:
            value = row[name]
            if name in BOOL_COLUMNS:
                values.append("1" if value else "0")
            elif name == "status":
                values.append(str(value))
            elif isinstance(value, float) and value != value:
                values.append("nan")
            else:
                values.append(f"{float(value):.17g}")
        lines.append(",".join(values))
    return "\n".join(lines) + "\n"


def write_simulink_export(
    rows: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write eesm_lut.csv and eesm_lut_metadata.json after validation."""
    normalized = validate_export_rows(rows, metadata)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    csv_text = render_lut_csv(normalized)
    csv_bytes = csv_text.encode("ascii")
    csv_path = output_root / "eesm_lut.csv"
    csv_path.write_bytes(csv_bytes)

    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": "simulink_corroboration_export",
        "not_electromagnetic_truth": True,
        "fem_audit_complete": bool(metadata.get("fem_audit_complete", False)),
        "candidate_id": metadata.get("candidate_id"),
        "audit_model_sha256": metadata["audit_model_sha256"],
        "model_sha256": metadata["model_sha256"],
        "lut_sha256": _sha256_bytes(csv_bytes),
        "n_rows": len(normalized),
        "columns": list(EXPORT_COLUMNS),
        "source": metadata.get("source", ""),
        "notes": metadata.get("notes", ""),
    }
    meta_path = output_root / "eesm_lut_metadata.json"
    meta_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def export_scheduler_candidate(
    schedule_path: str | Path,
    model_metadata_path: str | Path,
    output_dir: str | Path,
    candidate_id: str,
) -> dict[str, Any]:
    """Export one candidate's offline schedules as a Simulink LUT."""
    payload = json.loads(Path(schedule_path).read_text(encoding="utf-8"))
    model_meta = json.loads(Path(model_metadata_path).read_text(encoding="utf-8"))
    artifact_sha = str(model_meta["artifact_sha256"])
    rows = []
    for source in payload["schedules"]:
        if source.get("candidate_id") != candidate_id:
            continue
        status = str(source["status"])
        schedulable = status in SCHEDULABLE
        rows.append(
            {
                "rpm_mech": source["omega_rpm"],
                "t_ref_nm": source["t_ref_nm"],
                "id_ref_a": source.get("id_ref_a"),
                "iq_ref_a": source.get("iq_ref_a"),
                "if_ref_a": source.get("if_ref_a"),
                "status": status,
                "torque_ok": bool(source.get("torque_ok", False)),
                "voltage_ok": bool(source.get("voltage_ok", False)),
                "stator_current_ok": bool(source.get("stator_current_ok", False)),
                "field_current_ok": bool(source.get("field_current_ok", False)),
                "domain_ok": bool(source.get("domain_ok", False)),
                "uncertainty_ok": schedulable,
            }
        )
    if not rows:
        raise SimulinkExportRefusal(f"no schedules for {candidate_id}")
    metadata = {
        "candidate_id": candidate_id,
        "audit_model_sha256": artifact_sha,
        "model_sha256": artifact_sha,
        "fem_audit_complete": False,
        "source": str(schedule_path),
        "notes": (
            "Offline copper-loss schedules. Not a prospective FEM audit. "
            "Simulink results are corroboration only."
        ),
    }
    return write_simulink_export(rows, metadata, output_dir)
