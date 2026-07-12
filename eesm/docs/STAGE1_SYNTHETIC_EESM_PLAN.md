# Stage 1 — Synthetic EESM test harness (plan)

**Status:** offline foundry and synthetic comparison path complete; not a finished research result.
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
Legacy synthetic-map coefficients and runner settings live in `eesm/configs/synthetic_eesm_manifest.json`; the foundry source of truth for experiment domains, roles, budgets, gates, seeds, schemas, and paths is `eesm/configs/eesm_experiment_manifest.json`.

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

## Baseline sampling strategies

Tasks 1–2 implement three approved generators:

1. **Tensor grid** — full factorial, good baseline, expensive in 3D.  
2. **Random** — seeded uniform box samples.  
3. **Latin hypercube** — space-filling (SciPy `qmc` when available).

Sequential or uncertainty-guided sampling is not implemented and is explicitly disabled in the foundry manifest until all non-adaptive baselines pass.

**Implemented comparison contract:**

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
6. Sample CSV schema remains stable: `point_id, role, source, region, id_a, iq_a, if_a, lambda_d_wb, lambda_q_wb, solver_status, converged, provenance_id, strategy, budget, seed`.
7. Surrogate train/compare loop reuses clean interfaces.
8. Maxwell handoff is written and remains manual/prospective.
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
  run_synthetic_stage1.py          # one-command synthetic runner
  run_equal_budget_study.py        # frozen baseline comparison matrix
  configs/eesm_experiment_manifest.json  # foundry source of truth
  configs/synthetic_eesm_manifest.json   # legacy synthetic runner/map settings
  src/
    data/experiment_points.py
    synthetic/synthetic_map.py
    sampling/sample_designs.py
    surrogates/
    experiments/equal_budget.py
    scheduler/copper_loss_scheduler.py
    validation/
    lut/audit.py
  tests/
  docs/STAGE1_SYNTHETIC_EESM_PLAN.md
out/eesm/                # generated artifacts outside source
```

## Commands

From the **repo root**:

```pwsh
# One-command Stage 1 synthetic harness (oracle + samples + smoke + scheduler demo)
python eesm/run_synthetic_stage1.py

# Or with the project venv:
.\.venv\Scripts\python eesm/run_synthetic_stage1.py
.\.venv\Scripts\python eesm/run_equal_budget_study.py

# Tests
.\.venv\Scripts\python -m pytest tests -q
.\.venv\Scripts\python -m pytest eesm/tests -q
```

Artifacts land under `out/eesm/`:

| File | Content |
|------|---------|
| `oracle_dense_map.csv` | Dense synthetic truth grid |
| `samples_tensor_grid.csv` | Tensor product design |
| `samples_random.csv` | Seeded random design |
| `samples_latin_hypercube.csv` | Space-filling LHS design |
| `stage1_synthetic_summary.json` | Machine-readable Stage 1 summary |

Optional overrides:

```pwsh
python eesm/run_synthetic_stage1.py --out path\to\temp_out --oracle-n-id 11
```

## What is intentionally out of scope (this pass)

- Real FEM-backed model leaderboard and release decision
- Real Maxwell/AEDT EESM geometry and parametric sweeps  
- Field-flux \(\lambda_f\) identification  
- Flash-ready embedded FOC tables  

Those require synthetic qualification evidence, a reviewed Maxwell runbook, frozen foundry gates and numerical thresholds, and independent validation. Simulink/controller readiness is not yet established.
