# EESM experiment pipeline architecture

## Status and boundary

The EESM foundry supports deterministic synthetic studies, four surrogate
families, controller-aware metrics, frozen promotion gates, constrained
scheduling, and prospective LUT audit joins. Numerical thresholds were
frozen on 2026-08-13 from `out/eesm/threshold_proposal_20260813.json`.
Promotion still requires a completed equal-budget fit; no LUT or
release claim is made.
Task 9 collected all 64 frozen real-FEM rows with complete evidence, no
adaptive non-convergence warnings, and at most 1,826 mesh elements. Canonical
normalization completed, but the Task 9 report fails the frozen torque-closure
gate: maximum residual is 42.474642129016004 N.m versus the 1.1 N.m limit.
Direct AEDT output-variable and torque-report paths agree, so the mismatch is a
physics/model-closure result rather than a scalar readback error. No
controller-ready LUT, threshold update, promotion, or Task 10 result is claimed.
The failure is broad: 59/64 rows exceed tolerance and every field-weakening row
fails, so downstream fitting cannot treat it as an isolated rejected sample.

Corrective model audit also invalidated the original model contract itself.
The saved conversion has 77.0793 mm depth instead of 120 mm; its RMxprt
conductor semantics resolve to 144 stator series turns per phase and 20 field
turns per pole instead of 36 and 80; and it retains a damper cage forbidden by
the geometry specification. The write-once `r2` diagnostic therefore stops
before physics solves. A corrected `r3` project subsequently passed source and
configuration checks, but rotating its already clipped quarter-sector sheets
for co-energy offsets caused geometry intersections and invalid periodic
topology. The separate full-machine direct `r4` model passed independent
inventory and AEDT design validation, then exceeded the AEDT Student mesh
limit on its first field-only solve. These are distinct preserved failures; no
replacement campaign is authorized. Any reduced-sector revision must prove
anti-periodicity and explicit full-machine scaling before it can qualify.

The Stage 0 IPM path remains frozen and separate. EESM code reuses shared
physics without changing the IPM manifest, scripts, policy, or outputs.

## Data and decision flow

```text
qualification -> freeze geometry, materials, mesh, conventions
train         -> equal-budget fits for every strategy/model/budget
selection     -> independent controller metrics -> all required gates
promotion     -> deterministic ranking, only after thresholds are frozen
promoted map  -> constrained scheduler -> frozen LUT audit commands
scheduler_audit -> manual Maxwell export -> offline release audit
```

Canonical point identities prevent overlap among `train`, `selection`,
`scheduler_audit`, and optional `reference` roles. Scheduler-audit results may
affect release acceptance only; they cannot influence sampling, fitting,
hyperparameters, budget selection, promotion, or refitting.
Task 9 may collect all four already-frozen audit rows for exact campaign
completion, but it keeps them sealed and unavailable to decisions until after
promotion. Its 64-point budget is the total `40/12/8/4` campaign allocation,
not a claim of 64 training rows.

## Supported implementation

```text
eesm/configs/eesm_experiment_manifest.json  foundry source of truth
eesm/schemas/                               point and result-bundle contracts
eesm/src/data/                              canonical identities and roles
eesm/src/sampling/                          frozen baseline designs
eesm/src/surrogates/                        four persisted model families
eesm/src/experiments/                       equal-budget matrix runner
eesm/src/validation/                        metrics, gates, promotion
eesm/src/scheduler/                         constrained copper-loss scheduler
eesm/src/lut/                               LUT and prospective FEM audit join
eesm/fem/README.md                          manual Maxwell handoff
out/eesm/                                   generated artifacts, outside source
```

## Runnable offline commands

```pwsh
.\.venv\Scripts\python -m pytest tests eesm/tests -q
.\.venv\Scripts\python eesm/run_synthetic_stage1.py
.\.venv\Scripts\python eesm/run_equal_budget_study.py
```

The equal-budget command produces synthetic comparison evidence, not a promoted
release: the canonical manifest intentionally keeps thresholds unfrozen until a
baseline campaign justifies numerical values. Follow `eesm/fem/README.md` only
after qualification is approved; never refit after audit commands are frozen.
