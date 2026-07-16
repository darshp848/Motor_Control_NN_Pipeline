# Motor-Control Foundry Instructions

This repository is the software authority for the motor-control learning program. The sibling `../Motor_Control_Learning_Research/` repository is downstream: it may document verified foundry outputs, but it must not redefine executable contracts, thresholds, roles, schemas, promotion decisions, or result provenance.

## Start Every Nontrivial Task With State Reconstruction

Before proposing or implementing a change:

1. Read `README.md`, `docs/EESM_PIPELINE_ARCHITECTURE.md`, and the most relevant current plan or qualification document.
2. Inspect `git status` and preserve unrelated or unfinished work.
3. Identify the authoritative manifest, schema, test, generated evidence, and current blocking gate for the requested outcome.
4. Restate the next bounded milestone, its acceptance evidence, and its stop condition. Translate a plain-language request into this contract; ask the user only for choices that materially affect intent, safety, or scope.

Use `.agents/skills/progress-motor-control-foundry/SKILL.md` for project progression, diagnosis, solver campaigns, surrogate work, controller artifacts, or research handoff.

## Authority and Evidence Boundaries

- `eesm/configs/eesm_experiment_manifest.json` is the source of truth for frozen roles, budgets, gates, seeds, schemas, and canonical paths.
- Source code, schemas, tests, and reviewed plans define intended behavior. Files under `out/` are generated evidence, not executable authority.
- Preserve frozen point identities, role separation, hashes, failed runs, raw evidence, and provenance. Never relabel, overwrite, or silently discard a failed campaign.
- Keep Stage 0 IPM artifacts separate from Stage 1 EESM work.
- Numerical acceptance thresholds remain `baseline_required` until independent baseline evidence supports freezing them. Do not weaken a gate to admit a preferred result.
- Do not claim a promoted surrogate, controller-ready LUT, released map, completed research result, or downstream training readiness without the exact verified artifacts required by the manifest and current plan.

## Stage Gates

Keep these stages separate and verify each before advancing:

1. research question and contract;
2. offline software and schema validation;
3. machine/model build and inventory validation;
4. geometry/design validation and initial mesh generation;
5. bounded field solve or data collection;
6. canonical normalization and provenance checks;
7. qualification and invariant evaluation;
8. surrogate fitting and independent selection;
9. deterministic promotion;
10. scheduler/LUT audit;
11. training, deployment, and research claims.

Do not start AEDT/Maxwell, Simulink, a long campaign, or model training unless the user requested that operation and every preceding gate is evidenced. For AEDT work, validate the saved model and generate the initial mesh before solving. If an external application crashes or the same failure repeats twice, stop mutations, preserve evidence, and re-check version-matched vendor documentation plus known-good local artifacts.

The current Task 9 plan is fail-closed. Read `docs/superpowers/plans/2026-07-15-task9-real-maxwell-baseline-campaign.md` before Task 9 work. Its failed torque-closure evidence must not be converted into Task 10 authorization.

## Execution Discipline

- Prefer the smallest diagnostic that distinguishes plausible causes before editing or launching an external tool.
- Separate validation, build, mesh, solve, normalization, fitting, and training into independently reviewable steps.
- Use the repository `.venv` for Python commands.
- Keep tests lean. Extend existing contract or regression cases when possible; do not add redundant per-point or geometry tests.
- Do not start Maxwell or Simulink, change frozen thresholds, or publish downstream claims unless the task explicitly authorizes it.
- Use subagents only when the user explicitly requests delegation. Give each a bounded, non-overlapping scope and require evidence-backed conclusions.

## Verification and Handoff

Run the narrowest relevant checks first, then broader checks only when justified. Common offline commands are:

```powershell
.\.venv\Scripts\python.exe -m pytest eesm/tests/test_maxwell_adapter.py -q
.\.venv\Scripts\python.exe -m pytest tests eesm/tests -q
```

Before declaring completion, report files changed, commands and outcomes, artifacts inspected or produced, passed and blocked gates, the next safe action, and anything intentionally not run.

Do not commit, push, launch external applications, or update the research repository unless the user explicitly asks.
