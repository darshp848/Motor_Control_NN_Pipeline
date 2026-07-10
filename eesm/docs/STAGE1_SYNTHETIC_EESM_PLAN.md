# Stage 1 — Synthetic EESM test harness (plan)

**Status:** synthetic scaffold (not a finished research result).  
**Goal:** prove the **EESM workflow** offline with a fake but physically reasonable map **before** spending Maxwell/AEDT 3D FEM hours.

## Why synthetic EESM comes before real Maxwell

Real EESM 3D FEM sweeps are slow, license-bound, and easy to misconfigure. If the **pipeline** has bugs (wrong units, broken scheduler constraints, bad sampling CSV schemas), you will burn FEM time on noise.

A **synthetic truth model** is:

- free and instant,
- deterministic (same inputs → same fluxes),
- fully known (you can check torque, voltage, and copper loss exactly),
- good enough to test sampling → surrogate → validation → scheduler → audit **logic**.

Only after that logic is solid do you attach real Maxwell sweeps.

## What the “fake” EESM map represents

The map is a smooth function:

\[
(i_d, i_q, i_f) \mapsto (\lambda_d, \lambda_q)
\]

It is **not** a fitted FEM surface. It encodes the qualitative physics we care about:

| Effect | How it appears |
|--------|----------------|
| Field excitation | Increasing \(i_f\) increases \(\lambda_d\) (mutual \(M_{df}\)) |
| Saturation | Inductance softens as \(\propto 1/(1+\alpha i^2)\) at high current |
| Cross-coupling | Small \(d\)–\(q\) and \(q\)–\(f\) terms |
| Smoothness | Continuous formulas so optimizers do not trip on noise |

Optionally later:

\[
(i_d, i_q, i_f) \mapsto (\lambda_d, \lambda_q, \lambda_f)
\]

**Units (Stage 1 defaults):** currents in A, flux in Wb, torque in N·m, voltages in V.  
Limits and coefficients live in `eesm/configs/synthetic_eesm_manifest.json`.

## What the copper-loss optimizer does

The **scheduler** turns a speed/torque command into current references:

\[
(\omega, T_{\mathrm{ref}}) \mapsto (i_{d,\mathrm{ref}}, i_{q,\mathrm{ref}}, i_{f,\mathrm{ref}})
\]

Physics used:

\[
T = \tfrac{3}{2} P\,(\lambda_d i_q - \lambda_q i_d)
\]

\[
v_d = R_s i_d - \omega_e \lambda_q,\quad
v_q = R_s i_q + \omega_e \lambda_d
\]

\[
P_{cu} = \tfrac{3}{2} R_s (i_d^2 + i_q^2) + R_f i_f^2
\]

Search finds the **lowest copper loss** among candidates that satisfy:

- torque within tolerance,
- stator current limit \(|I_s|\),
- field current min/max,
- stator voltage limit,
- map domain bounds.

Status labels (do not invent fake currents when the problem is impossible):

| Status | Meaning |
|--------|---------|
| `feasible` | All constraints satisfied; min \(P_{cu}\) among feasible |
| `saturated_to_boundary` | Torque met; at least one limit on the edge |
| `infeasible` | No point meets torque + hard limits |
| `out_of_domain` | No candidates inside domain/current box |
| `search_failed` | Numerical / internal failure |

**Important research stance:** the learned model does **not** replace FOC. It is a **flux-map surrogate / map-correction** tool used to build **validated controller-facing references** (LUTs / schedulers).

## How sampling strategies will be compared later

Stage 1 implements generators only:

1. **Tensor grid** — full factorial, good baseline, expensive in 3D.  
2. **Random** — seeded uniform box samples.  
3. **Latin hypercube** — space-filling (SciPy `qmc` when available).  
4. **Sequential / uncertainty** — **placeholder** with a documented TODO for active learning.

**Later comparison (not in this first pass):**

- train surrogates on each design under a **fixed FEM budget** \(N\),
- evaluate on a held-out dense oracle (synthetic first, then real FEM),
- rank by in-domain flux RMSE / torque error / scheduler regret,
- only then claim “strategy A is more data-efficient than B.”

## What must pass before real EESM Maxwell sweeps

Gate checklist:

1. Synthetic map returns finite fluxes; \(i_f \uparrow \Rightarrow \lambda_d \uparrow\) at a fixed point.  
2. Torque / voltage / \(P_{cu}\) formulas match the frozen conventions.  
3. Scheduler finds a **feasible** modest \(T_{\mathrm{ref}}\).  
4. Impossible \(T_{\mathrm{ref}}\) returns **`infeasible`** (no fake \(i_d,i_q,i_f\)).  
5. Seeds make sampling **repeatable**.  
6. CSV schemas stable (`oracle` and `samples` columns).  
7. (Next) Surrogate train/compare loop reuses clean interfaces.  
8. (Next) Maxwell **qualification runbook** written and reviewed.  
9. Only then: small real EESM pilot sweep → scale up.

## Connection to the publication direction

Long-term story:

> **Validation-gated, data-efficient EESM FEM → surrogate → LUT**  
> with copper-loss constrained current scheduling and prospective audit  
> **before** claiming controller-ready tables.

Publication-facing claims should rest on:

- independent validation (not train-set RMSE alone),
- domain-aware metrics (interpolation vs extrapolation),
- scheduler constraints that match hardware limits,
- audit trails (commands, seeds, hashes) like Stage 0 IPM.

Stage 1 is the **offline EESM dry-run** of that story. Stage 0 IPM remains the frozen template for process discipline.

## Layout

```text
eesm/
  configs/synthetic_eesm_manifest.json
  src/
    synthetic/synthetic_map.py
    sampling/sample_designs.py
    surrogates/          # placeholder for later ML comparison
    scheduler/copper_loss_scheduler.py
    validation/synthetic_validation.py
  tests/
  outputs/               # generated CSVs (local)
  docs/STAGE1_SYNTHETIC_EESM_PLAN.md
```

## Commands

```pwsh
# From repo root, with project venv:
.\.venv\Scripts\python -m pytest eesm/tests -q

# Optional smoke report:
.\.venv\Scripts\python -c "from pathlib import Path; import sys; sys.path.insert(0, 'eesm/src'); from validation.synthetic_validation import run_smoke_validation; import json; print(json.dumps(run_smoke_validation('eesm/configs/synthetic_eesm_manifest.json'), indent=2))"
```

## What is intentionally out of scope (this pass)

- Full multi-model surrogate leaderboard for EESM  
- Real Maxwell/AEDT EESM geometry and parametric sweeps  
- Field-flux \(\lambda_f\) identification  
- Flash-ready embedded FOC tables  

Those come **after** the synthetic harness and a Maxwell qualification runbook.
