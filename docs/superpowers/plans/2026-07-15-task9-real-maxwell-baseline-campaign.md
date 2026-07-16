# Task 9 Real Maxwell Baseline Campaign Plan

**Goal:** Produce the first frozen, provenance-complete real Maxwell EESM baseline dataset without making surrogate-promotion, controller-LUT, map-release, or Task 10 claims.

**Target:** primary checkout on `eesm-pipeline`; qualified project `aedt_mcp/tmp/aedt_projects/eesm_qual/eesm_qual.aedt`; design `EESM_2D_Qual`; setup `Setup_Qual`; solution `Setup_Qual : LastAdaptive`.

## Current offline status (do not over-claim)

- Freeze: complete and write-once (`frozen_points.csv` SHA-256 `3ce7f7bd4bc2abbe7aefb425d2923fa488286603c32ec506d20eecbbc361fb6d`).
- FEM: **64/64 frozen rows collected** with no solver errors or adaptive non-convergence warning. Maximum measured mesh is 1,826 elements. Earlier one- and two-pass attempts remain preserved under `out/eesm/task9_baseline/failed_runs/`.
- Canonical/report: canonical normalization completed. The report is intentionally `fail` because 59/64 rows exceed the frozen 1.1 N.m torque-closure limit, including all 13 field-weakening rows; maximum residual is 42.474642129016004 N.m. Every other report check passes.
- Claims: no promoted surrogate, controller-ready LUT, released map, or Task 10 result.
- Blocker: real physics/model closure. A no-solve/readback diagnostic was followed by a fresh point solve; `Torque_FEM` and direct `TorqueRotor.Torque` report values agreed exactly, so changing the exporter read path cannot clear the gate. Do not weaken the frozen tolerance or begin Task 10.
- Corrective preflight: the frozen ten-point `r2` diagnostic (anchors SHA-256 `6b48932724c31b09317b69b149847e5167c5151fc6bf79ca74c1cd2eea1cbbb3`) stops before solving. The saved model has 77.0793 mm depth, 144 stator series turns/phase, 20 field turns/pole, and a damper cage, rather than the frozen 120 mm, 36 turns/phase, 80 turns/pole, no-cage contract.
- Corrected-build status: the compliant RMxprt interpretation is 36 conductors/slot with four balanced stator branches and 160 active conductors/pole. A separate `r3` RMxprt solve completed and generated a converted-design autosave, but AEDT exited before configuration/status; reopening the preserved autosave non-graphically repeated the exit. No corrected project or FEM row is accepted.

## Corrective requalification required before another Task 9 campaign

1. Preserve this campaign and its failed report unchanged as the evidence that
   invalidated the seven-point pilot's campaign-wide torque assumption.
2. On a new model revision, compare virtual torque with an independent
   energy/co-energy derivative and phase-domain flux-linkage calculation at a
   predeclared compact set containing the worst boundary point, field-weakening
   anchors, and the original Task 8 points.
3. Audit stator winding polarity, linkage scaling, turns/conductors, model
   fraction handling, rotor-object membership, and the dq reference convention.
   Do not select a convention by minimizing errors on these 64 results.
4. If the model or convention changes, assign a new qualification revision,
   campaign ID, frozen point hash, and raw output root. Do not overwrite or
   relabel this campaign.
5. Repeat the expanded qualification pilot with an acceptance rule frozen
   before solving. Only a passing requalification may authorize a new 64-point
   campaign; Task 10 remains blocked.

Current stop: retain all `r2`/`r3` evidence and do not run the ten physics
anchors until a corrected project opens, records 120 mm depth, four phase
branches with 18 turns/coil, 80 field turns/pole, and no electrically active
damper cage, then validates without AEDT errors. A future retry must start
from a new preserved recovery copy, not overwrite a failed project.

## Frozen campaign contract

- Budget: exactly 64 energized FEM points in the total `40/12/8/4` campaign allocation. This reuses the smallest manifest budget numeral but is not a claim of 64 training rows; Task 9 does not expand to 128 or 256.
- Roles: 40 `train`, 12 `selection`, 8 `reference`, and 4 `scheduler_audit`.
- Seeds: train `20260710`, selection `20260711`, reference `20260712`, scheduler audit `2909`.
- Identity: the first 16 hexadecimal characters of SHA-256 over `Id|Iq|If`, with each current rounded and serialized to nine decimal places.
- Domain: `Id in [-120, 0] A_peak_dq`, `Iq in [0, 120] A_peak_dq`, `If in [0, 15] A_dc`.
- Sampling: reviewed boundary/field-weakening/saturation anchors plus independent role-specific Latin-hypercube interiors. The CSV is frozen and hashed before any Task 9 solve. FEM results must never revise it.
- Source-free origin: `(0,0,0)` is excluded from AEDT and remains an analytic invariant.

The frozen artifacts are:

- `out/eesm/task9_baseline/frozen_points.csv`
- `out/eesm/task9_baseline/campaign_freeze.json`

## Role boundaries

- `train`: may support later fitting, but Task 9 fits no surrogate.
- `selection`: independent from training and may support later model selection.
- `reference`: independent real-FEM evidence for later acceptance-threshold methodology.
- `scheduler_audit`: its four frozen rows are collected for exact campaign completion but prohibited from sampling, fitting, hyperparameter, budget, promotion, and Task 9 threshold decisions. Collection does not make the results available: they remain sealed until the manifest's post-promotion audit stage.

Point IDs and current tuples must be disjoint across all four roles. Role and region labels are immutable after the point file is frozen.

## AEDT execution and resume behavior

1. Use Computer Use to launch AEDT Student explicitly, open `eesm_qual.aedt`, and run `eesm/aedt/export_eesm_points.py` through **Automation -> Run Script**.
2. The exporter verifies the frozen point-file SHA-256 before touching AEDT.
3. It processes at most one new point, restores parametric winding expressions, saves the project, and writes status. AEDT Student 2025 R2 does not expose a working application-close method to this embedded script, so Computer Use closes the saved process immediately after the status check.
4. Use a fresh AEDT process for every new point. Never start another instance while one is active; verify the prior process is gone before relaunch.
5. After every invocation, read `out/eesm/task9_baseline/raw/campaign_status.json` and `campaign_progress.csv`. Continue only from `partial_resume_required` with an idle stage, consistent completed IDs, and no failure, restore error, AEDT error, or adaptive non-convergence warning. The first attempt's legacy `close_error: QuitApplication` records an unsupported embedded close method and does not override its separate adaptive-convergence failure.
6. Resume rejects malformed headers, duplicate/unknown rows, failed rows, current/role/identity drift, machine-metadata drift, and missing raw evidence.

The exporter persists `active_point` and `stage` before current mutation, analysis, flux export, torque extraction, and solver-evidence export. A failed row remains a fail-closed stop; it is never silently retried or removed.

## Raw and canonical outputs

Local-only raw evidence:

- `out/eesm/task9_baseline/raw/campaign_progress.csv`
- `out/eesm/task9_baseline/raw/campaign_status.json`
- `out/eesm/task9_baseline/raw/point_exports/*_flux_abc.csv`
- `out/eesm/task9_baseline/raw/solver_evidence/*_mesh.ms`
- `out/eesm/task9_baseline/raw/solver_evidence/*_convergence.conv`

Reviewed small canonical evidence:

- `out/eesm/task9_baseline/canonical_campaign.csv`
- `out/eesm/task9_baseline/campaign_report.json`

Every canonical row must carry point ID, immutable role/region, `Id/Iq/If`, `lambda_d/lambda_q`, raw `Torque_FEM`, translated controller torque (`-Torque_FEM`), pole pairs, rotor position, project/design/setup, provenance ID, raw-progress and raw-row hashes, raw evidence paths, measured mesh/pass counts, solver status/message, and explicit units.

## Gates and stopping rules

Stop immediately and preserve evidence if any of these occurs:

- another AEDT process is active;
- point-file hash or frozen identity/role/current validation fails;
- a prior progress row is failed, duplicated, malformed, unknown, inconsistent, or missing evidence;
- the active project/design/setup differs from the qualified target;
- AEDT analysis returns a failure or unresolved error message;
- AEDT reports that adaptive passes did not converge based on the specified criteria;
- flux or torque is non-finite;
- measured mesh exceeds 1,950 elements, convergence evidence is missing, or adaptive passes are non-positive;
- winding restoration, project save, status write, or clean close fails.

Campaign completion requires exactly 64 unique requested rows and 64 qualifying converged rows, no adaptive non-convergence warning, consistent units and two pole pairs, cryptographically bound raw evidence, and Task 8 torque closure (`controller torque = -Torque_FEM`, maximum residual at most 1.1 N.m).

## Threshold-freezing procedure

The report computes only quantities supported by the frozen campaign. A zero failed-row QA rate may be proposed if all checks pass. Region, torque, voltage, and feasibility acceptance thresholds require later frozen surrogate predictions and independent error distributions; Task 9 must leave those values `null`. Because the result-bundle schema requires all numerical thresholds together, the canonical manifest remains `baseline_required`. No threshold may be tuned to admit a preferred surrogate, and scheduler-audit rows are excluded from the decision.

## Lean test budget

- Keep `eesm/tests/test_maxwell_adapter.py` at exactly four collected cases.
- Extend assertions inside its existing parameterized cases for the Task 9 controller-torque and exporter/report source contracts.
- Add no geometry tests, per-point tests, or new collected test cases.
- Compile all changed Python scripts, run the four-case adapter check, then the full suite once before commit.

## Safe offline inspection during partial progress

```powershell
Get-Content out/eesm/task9_baseline/campaign_freeze.json
Get-Content out/eesm/task9_baseline/raw/campaign_status.json
Get-Content out/eesm/task9_baseline/raw/campaign_progress.csv
```

## Operator commands only after 64/64 qualifying GUI invocations

```powershell
.\.venv\Scripts\python.exe eesm/aedt/normalize_eesm_results.py `
  out/eesm/task9_baseline/raw/campaign_progress.csv `
  out/eesm/task9_baseline/frozen_points.csv `
  out/eesm/task9_baseline/canonical_campaign.csv

.\.venv\Scripts\python.exe eesm/aedt/report_task9_campaign.py `
  out/eesm/task9_baseline/frozen_points.csv `
  out/eesm/task9_baseline/raw/campaign_progress.csv `
  out/eesm/task9_baseline/canonical_campaign.csv `
  out/eesm/task9_baseline/campaign_report.json
```

Task 9 ends after reviewed evidence, documentation, verification, commit, push, and local/remote HEAD equality. Do not begin Task 10.
