# EESM experiment pipeline architecture

## Status and boundary

The EESM foundry supports deterministic synthetic studies, four surrogate
families, controller-aware metrics, frozen promotion gates, constrained
scheduling, and prospective LUT audit joins. Numerical thresholds remain
`baseline_required`, so promotion and real-release claims remain blocked.
Maxwell execution is manual; no FEM campaign or controller-ready LUT is claimed.

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
