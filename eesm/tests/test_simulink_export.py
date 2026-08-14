"""Task 10 Simulink LUT export contract. No MATLAB launch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from export.simulink_export import (
    SimulinkExportRefusal,
    validate_export_rows,
    write_simulink_export,
)


HASH = "a" * 64


def _row(**overrides):
    row = {
        "rpm_mech": 1000.0,
        "t_ref_nm": 10.0,
        "id_ref_a": -5.0,
        "iq_ref_a": 20.0,
        "if_ref_a": 4.0,
        "status": "feasible",
        "torque_ok": True,
        "voltage_ok": True,
        "stator_current_ok": True,
        "field_current_ok": True,
        "domain_ok": True,
        "uncertainty_ok": True,
    }
    row.update(overrides)
    return row


def _meta(**overrides):
    meta = {"audit_model_sha256": HASH, "model_sha256": HASH}
    meta.update(overrides)
    return meta


def test_valid_export_writes_lut_and_metadata(tmp_path: Path) -> None:
    payload = write_simulink_export(
        [_row(), _row(rpm_mech=3000.0, t_ref_nm=31.83)],
        _meta(candidate_id="demo|256|rbf_or_gp"),
        tmp_path,
    )
    csv_path = tmp_path / "eesm_lut.csv"
    meta_path = tmp_path / "eesm_lut_metadata.json"
    assert csv_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["n_rows"] == 2
    assert meta["lut_sha256"] == payload["lut_sha256"]
    assert meta["not_electromagnetic_truth"] is True
    text = csv_path.read_text(encoding="ascii")
    assert text.splitlines()[0].startswith("rpm_mech,t_ref_nm,id_ref_a")


def test_refuses_duplicate_keys_and_missing_masks() -> None:
    with pytest.raises(SimulinkExportRefusal, match="duplicate"):
        validate_export_rows([_row(), _row()], _meta())
    missing = _row()
    del missing["voltage_ok"]
    with pytest.raises(SimulinkExportRefusal, match="missing columns"):
        validate_export_rows([missing], _meta())


def test_refuses_invalid_status_currents_and_hash_mismatch() -> None:
    with pytest.raises(SimulinkExportRefusal, match="invalid status"):
        validate_export_rows([_row(status="promoted")], _meta())
    with pytest.raises(SimulinkExportRefusal, match="id_ref_a must be finite"):
        validate_export_rows([_row(id_ref_a=float("nan"))], _meta())
    with pytest.raises(SimulinkExportRefusal, match="hash mismatch"):
        validate_export_rows([_row()], _meta(model_sha256="b" * 64))
