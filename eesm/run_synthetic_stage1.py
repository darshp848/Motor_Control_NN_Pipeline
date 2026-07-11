#!/usr/bin/env python
"""One-command Stage 1 synthetic EESM harness runner.

Loads the synthetic manifest, writes oracle + sample CSVs, runs smoke
validation and example scheduler commands, and writes a JSON summary.

Does not launch AEDT / Maxwell.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Repo-local imports: eesm/src on path
_EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_EESM_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from sampling.sample_designs import (  # noqa: E402
    latin_hypercube_samples,
    random_samples,
    tensor_grid_samples,
    write_samples_csv,
)
from scheduler.copper_loss_scheduler import (  # noqa: E402
    CopperLossScheduler,
    SchedulerLimits,
    SchedulerResult,
)
from synthetic.synthetic_map import load_map_from_manifest  # noqa: E402
from validation.synthetic_validation import (  # noqa: E402
    run_smoke_validation,
    write_json_summary,
)

DEFAULT_MANIFEST = os.path.join(
    _EESM_ROOT, "configs", "synthetic_eesm_manifest.json"
)
DEFAULT_OUTPUTS = os.path.join(_EESM_ROOT, "outputs")


def load_manifest(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_synthetic_truth_provider(manifest_path: str = DEFAULT_MANIFEST):
    """Build the deterministic truth provider shared by Stage 1 studies."""
    return load_map_from_manifest(manifest_path=os.path.abspath(manifest_path))


def resolve_output_dir(manifest: dict, output_dir: Optional[str] = None) -> str:
    """Resolve artifact directory (always absolute)."""
    if output_dir:
        return os.path.abspath(output_dir)
    # Default: eesm/outputs next to this script (stable regardless of cwd)
    _ = manifest  # reserved for future path overrides
    return os.path.join(_EESM_ROOT, "outputs")


def build_scheduler(fmap, manifest: dict) -> CopperLossScheduler:
    m = manifest.get("machine", {})
    s = manifest.get("scheduler", {})
    limits = SchedulerLimits(
        rs_ohm=float(m.get("rs_ohm", 0.05)),
        rf_ohm=float(m.get("rf_ohm", 8.0)),
        vdc_v=float(m.get("vdc_v", 400.0)),
        i_s_max_peak_a=float(m.get("i_s_max_peak_a", 120.0)),
        i_f_min_a=float(m.get("i_f_min_a", 0.0)),
        i_f_max_a=float(m.get("i_f_max_a", 15.0)),
        pole_pairs=int(m.get("pole_pairs", 2)),
        torque_tolerance_nm=float(s.get("torque_tolerance_nm", 0.5)),
    )
    return CopperLossScheduler(
        fmap,
        limits=limits,
        n_grid_id=int(s.get("n_grid_id", 25)),
        n_grid_iq=int(s.get("n_grid_iq", 25)),
        n_grid_if=int(s.get("n_grid_if", 12)),
        n_random_refine=int(s.get("n_random_refine", 200)),
        seed=int(s.get("seed", 0)),
    )


def run_stage1(
    manifest_path: str = DEFAULT_MANIFEST,
    output_dir: Optional[str] = None,
    oracle_n_id: int = 21,
    oracle_n_iq: int = 21,
    oracle_n_if: int = 11,
    feasible_rpm: float = 1500.0,
    feasible_t_ref: float = 20.0,
    infeasible_rpm: float = 1500.0,
    infeasible_t_ref: float = 1.0e6,
) -> Dict[str, Any]:
    """Run the Stage 1 synthetic pipeline. Returns summary dict.

    Writes artifacts under output_dir (testable with a temp path).
    """
    manifest_path = os.path.abspath(manifest_path)
    manifest = load_manifest(manifest_path)
    out_dir = resolve_output_dir(manifest, output_dir)
    os.makedirs(out_dir, exist_ok=True)

    fmap = build_synthetic_truth_provider(manifest_path)

    # --- oracle ---
    oracle_path = os.path.join(out_dir, "oracle_dense_map.csv")
    fmap.write_oracle_csv(
        oracle_path, n_id=oracle_n_id, n_iq=oracle_n_iq, n_if=oracle_n_if
    )
    n_oracle = oracle_n_id * oracle_n_iq * oracle_n_if

    # --- sampling ---
    samp = manifest.get("sampling", {})
    seed = int(samp.get("seed", 0))
    tensor_cfg = samp.get("tensor", {})
    n_random = int(samp.get("n_random", 500))
    n_lhs = int(samp.get("n_lhs", 500))

    domain = fmap.domain
    samples_written = {}

    tensor = tensor_grid_samples(
        domain,
        n_id=int(tensor_cfg.get("n_id", 8)),
        n_iq=int(tensor_cfg.get("n_iq", 8)),
        n_if=int(tensor_cfg.get("n_if", 5)),
        seed=seed,
    )
    p_tensor = os.path.join(out_dir, "samples_tensor_grid.csv")
    write_samples_csv(p_tensor, tensor)
    samples_written["tensor_grid"] = {
        "path": p_tensor,
        "n": int(len(tensor["id_a"])),
    }

    rnd = random_samples(domain, n=n_random, seed=seed)
    p_rnd = os.path.join(out_dir, "samples_random.csv")
    write_samples_csv(p_rnd, rnd)
    samples_written["random"] = {"path": p_rnd, "n": int(len(rnd["id_a"]))}

    lhs = latin_hypercube_samples(domain, n=n_lhs, seed=seed)
    p_lhs = os.path.join(out_dir, "samples_latin_hypercube.csv")
    write_samples_csv(p_lhs, lhs)
    samples_written["latin_hypercube"] = {
        "path": p_lhs,
        "n": int(len(lhs["id_a"])),
        "strategy_tag": str(lhs["strategy"][0]),
    }

    # --- smoke validation ---
    smoke = run_smoke_validation(manifest_path=manifest_path, fmap=fmap)

    # --- scheduler examples ---
    sched = build_scheduler(fmap, manifest)
    feasible_res: SchedulerResult = sched.schedule(feasible_rpm, feasible_t_ref)
    infeasible_res: SchedulerResult = sched.schedule(
        infeasible_rpm, infeasible_t_ref
    )

    summary: Dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_path": manifest_path,
        "experiment_id": manifest.get("experiment_id"),
        "output_dir": out_dir,
        "oracle": {
            "path": oracle_path,
            "n_rows": n_oracle,
            "n_id": oracle_n_id,
            "n_iq": oracle_n_iq,
            "n_if": oracle_n_if,
        },
        "samples": samples_written,
        "smoke_validation": smoke,
        "scheduler": {
            "feasible_example": feasible_res.to_dict(),
            "infeasible_example": infeasible_res.to_dict(),
        },
        "map": fmap.to_dict(),
        "status": "ok" if smoke.get("ok") else "smoke_failed",
    }

    summary_path = os.path.join(out_dir, "stage1_synthetic_summary.json")
    write_json_summary(summary_path, summary)
    summary["summary_path"] = summary_path
    return summary


def print_report(summary: Dict[str, Any]) -> None:
    print("=== Stage 1 synthetic EESM ===")
    print(f"manifest:  {summary.get('manifest_path')}")
    print(f"output:    {summary.get('output_dir')}")
    print(f"status:    {summary.get('status')}")
    o = summary.get("oracle", {})
    print(f"oracle:    {o.get('n_rows')} rows -> {o.get('path')}")
    for name, info in summary.get("samples", {}).items():
        print(f"samples[{name}]: n={info.get('n')} -> {info.get('path')}")
    smoke = summary.get("smoke_validation", {})
    print(f"smoke_ok:  {smoke.get('ok')}")
    fe = summary.get("scheduler", {}).get("feasible_example", {})
    print(
        "feasible:  status={status} id={id_ref_a:.3f} iq={iq_ref_a:.3f} "
        "if={if_ref_a:.3f} T={torque_nm:.3f} Pcu={p_cu_w:.2f}".format(
            status=fe.get("status"),
            id_ref_a=fe.get("id_ref_a") or 0.0,
            iq_ref_a=fe.get("iq_ref_a") or 0.0,
            if_ref_a=fe.get("if_ref_a") or 0.0,
            torque_nm=fe.get("torque_nm") or 0.0,
            p_cu_w=fe.get("p_cu_w") or 0.0,
        )
        if fe.get("id_ref_a") is not None
        else f"feasible:  status={fe.get('status')} (no refs)"
    )
    print(
        "  flags:    torque_ok={torque_ok} voltage_ok={voltage_ok} "
        "Is_ok={stator_current_ok} If_ok={field_current_ok} "
        "domain_ok={domain_ok}".format(**{
            k: fe.get(k) for k in (
                "torque_ok", "voltage_ok", "stator_current_ok",
                "field_current_ok", "domain_ok",
            )
        })
    )
    ie = summary.get("scheduler", {}).get("infeasible_example", {})
    print(
        f"infeasible: status={ie.get('status')} refs=None "
        f"msg={ie.get('message', '')[:80]}"
    )
    print(
        "  flags:    torque_ok={torque_ok} voltage_ok={voltage_ok} "
        "Is_ok={stator_current_ok} If_ok={field_current_ok} "
        "domain_ok={domain_ok}".format(**{
            k: ie.get(k) for k in (
                "torque_ok", "voltage_ok", "stator_current_ok",
                "field_current_ok", "domain_ok",
            )
        })
    )
    print(f"summary:   {summary.get('summary_path')}")


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--config",
        default=DEFAULT_MANIFEST,
        help="Path to synthetic_eesm_manifest.json",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Output directory (default: eesm/outputs)",
    )
    p.add_argument("--oracle-n-id", type=int, default=21)
    p.add_argument("--oracle-n-iq", type=int, default=21)
    p.add_argument("--oracle-n-if", type=int, default=11)
    ns = p.parse_args(argv)

    summary = run_stage1(
        manifest_path=ns.config,
        output_dir=ns.out,
        oracle_n_id=ns.oracle_n_id,
        oracle_n_iq=ns.oracle_n_iq,
        oracle_n_if=ns.oracle_n_if,
    )
    print_report(summary)
    return 0 if summary.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
