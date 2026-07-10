"""Experiment manifest load/save, file hashes, run metadata."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


# Required keys for the clean motor-params surface used by MTPA / audit.
MOTOR_PARAMS_REQUIRED_KEYS = (
    "poles",
    "pole_pairs",
    "rs_ohm",
    "vdc_v",
    "i_max_peak_a",
    "i_rated_peak_a",
    "rated_current_rms_a",
    "t_rated_nm",
    "flux_scale",
    "omega_mech_base_rpm",
    "omega_mech_max_rpm",
    "current_units",
    "dq_convention",
    "park_theta_re",
    "torque_formula",
    "voltage_formula",
    "v_max_formula",
    "flux_scale_definition",
    "phi_csv_scaling",
)


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, payload: dict, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=indent)
        f.write("\n")


def validate_motor_params(params: dict, strict: bool = True) -> List[str]:
    missing = [k for k in MOTOR_PARAMS_REQUIRED_KEYS if k not in params]
    if strict and missing:
        raise ValueError("motor params missing keys: " + ", ".join(missing))
    return missing


def clean_motor_params_from_raw(raw: dict, defaults: Optional[dict] = None) -> dict:
    """Project noisy AEDT pull output into the clean schema."""
    defaults = defaults or {}
    poles = int(raw.get("poles") or defaults.get("poles") or 4)
    pole_pairs = int(raw.get("pole_pairs") or poles // 2)
    out = {
        "poles": poles,
        "pole_pairs": pole_pairs,
        "rs_ohm": float(raw.get("rs_ohm", defaults.get("rs_ohm", 2.15938))),
        "vdc_v": float(raw.get("vdc_v", defaults.get("vdc_v", 311.0))),
        "i_max_peak_a": float(
            raw.get("i_max_peak_a", defaults.get("i_max_peak_a", 6.0))
        ),
        "i_rated_peak_a": float(
            raw.get(
                "i_rated_peak_a",
                raw.get("rated_current_peak_a", defaults.get("i_rated_peak_a", 4.009)),
            )
        ),
        "rated_current_rms_a": float(
            raw.get(
                "rated_current_rms_a",
                defaults.get("rated_current_rms_a", 2.83481),
            )
        ),
        "t_rated_nm": float(raw.get("t_rated_nm", defaults.get("t_rated_nm", 2.89531))),
        "flux_scale": float(raw.get("flux_scale", defaults.get("flux_scale", 1.0))),
        "omega_mech_base_rpm": float(
            raw.get(
                "omega_mech_base_rpm",
                defaults.get("omega_mech_base_rpm", 1800.0),
            )
        ),
        "omega_mech_max_rpm": float(
            raw.get(
                "omega_mech_max_rpm",
                defaults.get("omega_mech_max_rpm", 6000.0),
            )
            or defaults.get("omega_mech_max_rpm", 6000.0)
        ),
        "current_units": "peak_amperes_dq",
        "dq_convention": "motor_Park_theta_re_0_d_aligned_PhaseA",
        "park_theta_re": 0.0,
        "torque_formula": "T = (3/2) * pole_pairs * (Phi_d*Iq - Phi_q*Id)",
        "voltage_formula": (
            "Vd = Rs*Id - we*Phi_q; Vq = Rs*Iq + we*Phi_d; "
            "we = omega_mech_rad_s * pole_pairs"
        ),
        "v_max_formula": "V_max_phase_peak = Vdc / sqrt(3)  # SVPWM",
        "flux_scale_definition": (
            "flux_scale = T_rated / T_implied at (Id=0, Iq=I_rated_peak) "
            "using FEM Phi and pole_pairs; multiply FEM Phi by flux_scale "
            "before torque/voltage in MTPA"
        ),
        "phi_csv_scaling": "raw_FEM_unscaled; scale applied only in MTPA FluxSurrogate",
        "flux_scale_explanation": raw.get("flux_scale_explanation"),
        "source_raw_params": raw.get("source_raw_params"),
        "project": raw.get("project"),
        "design": raw.get("design"),
    }
    validate_motor_params(out, strict=True)
    return out


def package_versions(names: Iterable[str]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for name in names:
        try:
            mod = __import__(name)
            out[name] = getattr(mod, "__version__", "unknown")
        except Exception:
            out[name] = None
    return out


def build_run_manifest(
    *,
    config: dict,
    stages: List[str],
    file_hashes: Dict[str, str],
    seeds: dict,
    inference_model: Optional[str],
    extra: Optional[dict] = None,
) -> dict:
    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "package_versions": package_versions(
            ("numpy", "pandas", "scipy", "sklearn", "torch", "matplotlib")
        ),
        "stages": stages,
        "seeds": seeds,
        "file_hashes": file_hashes,
        "inference_model": inference_model,
        "config": config,
    }
    if extra:
        payload["extra"] = extra
    return payload


def load_experiment_manifest(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return load_json(path)


def default_manifest_path() -> str:
    return os.path.join("configs", "ipm_experiment_manifest.json")
