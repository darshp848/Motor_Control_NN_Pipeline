# Maxwell EESM qualification gate

Task 8 qualification completed on 2026-07-15. Seven energized Maxwell points
are assigned the frozen `reference` role and remain separate from training,
selection, and the current LUT `scheduler_audit` workflow. The source-free
origin is an analytic zero-current invariant: AEDT Student reproducibly exits
inside `Analyze("Setup_Qual")` for that redundant solve, so no FEM row is
fabricated for it.

The RMxprt-first builder uses AEDT's built-in `steel_1008` for both cores,
recorded as academic material revision `rmxprt-steel_1008-r1`. This is a
reproducible benchmark choice, not a claim that the machine represents a
particular commercial lamination grade.

## Historical Task 8 manual sequence

The sequence below records how the frozen Task 8 artifacts were produced. The
current `export_eesm_points.py` is now the Task 9 campaign exporter and must
not be used to recreate the old smoke/pilot paths. New FEM work follows the
Task 9 plan and writes under `out/eesm/task9_baseline/`.

1. In AEDT Student 2025 R2, run `eesm/aedt/build_canonical_eesm.py` through
   **Automation -> Run Script**. The embedded script follows the IPM pipeline:
   it seeds the project from AEDT Student's installed
   `Examples/RMxprt/manual/SynM3_6p50Hz538kW.aedt`, just as the IPM pipeline
   seeded from the installed IPM example, then uses the active AEDT process and
   native RMxprt API. There is no external Python process or second AEDT
   window. The superseded hand-created project is preserved once as
   `eesm_qual.pre_synm_template.aedt`.

   Like the proven IPM project flow, it creates a TPSM RMxprt design, solves
   that analytical setup because conversion requires it, then automatically
   creates `EESM_2D_Qual` in Maxwell 2-D. It writes
   `eesm/aedt/eesm_model_build_status.json`, saves
   `aedt_mcp/tmp/aedt_projects/eesm_qual/eesm_qual.aedt`, leaves AEDT open for
   review, and never solves the Maxwell design. Stop unless status is `built`,
   `rmxprt_solve_attempted` is `true`, and `maxwell_solve_attempted` is `false`.
2. Confirm the builder status records the post-conversion qualification
   contract: magnetostatic XY, `Setup_Qual`, `Setup_Qual : LastAdaptive`,
   `Id/Iq/If`, dq-to-ABC phase currents, `TorqueRotor`, `Torque_FEM`, two pole
   pairs, and the 180 electrical-degree RMxprt alignment. The builder retains
   the native converted geometry but replaces its voltage-driven transient
   setup; transient RMxprt output must not be used as qualification data.
3. Historically, the Task 8 version of `eesm/aedt/export_eesm_points.py` was run manually through
   **Automation -> Run Script**. The script is resumable and records one row per
   attempted solve, including failures; it does not launch or attach AEDT. Flux
   is exported through the proven PhaseA/B/C flux-linkage data table, checked
   for a nonempty file, then converted to dq. It aborts after a solve failure.
   After each solve, the exporter writes convergence and mesh-statistics files
   and derives the actual triangle and adaptive-pass counts from that evidence.
   The script refuses rows with missing solver evidence.
   It also refuses to resume a progress file containing any failed row. Run at
   most one new point in each fresh AEDT process; the exporter persists its
   active point and stage before risky calls so an AEDT process exit remains
   diagnosable.
4. The historical first run was a four-point 2x2 smoke only: `field_only`, `q_current`,
   `negative_d`, and `combined_rated`, all at `If=2 A`. Inspect the status JSON,
   progress CSV, and four ABC exports, then stop. Set `SMOKE_APPROVED=True` only
   after primary review; later fresh AEDT sessions resume the remaining three
   energized pilot points.
5. The resulting `eesm_qualification_progress.csv` remains preserved as raw evidence. Its AEDT names
   and units are deliberately not canonicalized in place.
6. Run the offline normalizer, then qualifier:

   ```powershell
   .\.venv\Scripts\python.exe eesm/aedt/normalize_eesm_results.py eesm/aedt/eesm_qualification_progress.csv eesm/aedt/eesm_qualification_points.csv <canonical.csv>
   .\.venv\Scripts\python.exe eesm/aedt/qualify_eesm_project.py <canonical.csv> <qualification_report.json>
   ```

   Inspect GUI evidence with:

   ```powershell
   Get-Content eesm/aedt/eesm_qualification_export_status.json
   Get-Content eesm/aedt/eesm_qualification_progress.csv
   Get-ChildItem eesm/aedt/point_exports/*_flux_abc.csv
   ```

Blank mesh-element, adaptive-pass, or torque fields are retained as null rather
than fabricated. Missing mesh/adaptive evidence makes its qualification check
inconclusive. The qualification CLI exits nonzero for either fail or
inconclusive; library callers may inspect the returned report directly.

Each qualification check reports `pass`, `fail`, or `inconclusive`. The
verified report at `out/eesm/qualification/qualification_report.json` records
seven converged points and `overall_status: pass`; each measured mesh has 1350
elements and one adaptive pass. The RMxprt rotor orientation freezes
`controller torque = -Torque_FEM`. Against the controller-facing peak-current
relation `1.5*p*(lambda_d*Iq-lambda_q*Id)`, the observed maximum absolute
residual is 1.0369609944554 N.m, within the frozen 1.1 N.m Task 8 tolerance.
This unblocked the Task 9 software/campaign start but did not guarantee closure
over the broader frozen current domain. The completed 64-row Task 9 campaign
later observed a 42.474642129016004 N.m maximum residual, so the Task 8 pilot
was insufficient to establish campaign-wide torque closure. In total, 59/64
rows exceed tolerance and all 13 field-weakening rows fail. The frozen 1.1 N.m
tolerance remains unchanged and Task 9 reports `fail`.

Task 8 used the qualified one-pass `LastAdaptive` extraction contract. Task 9
preserves that historical result but applies a stricter campaign rule: an AEDT
warning that adaptive passes did not meet the specified criteria is
non-qualifying even when `Analyze` returns normally and finite outputs exist.
The first Task 9 attempt exposed that warning and is preserved locally; it was
not counted. The restarted campaign subsequently collected 64/64 converged
rows with measured evidence, then stopped at the independent torque-closure
gate. See
`docs/superpowers/plans/2026-07-15-task9-real-maxwell-baseline-campaign.md`.

## Corrective requalification evidence (2026-07-16)

The original Task 8 pass is historical evidence, not current model approval.
The Task 9 failure triggered a write-once ten-point `r2` diagnostic freeze
(anchors SHA-256
`6b48932724c31b09317b69b149847e5167c5151fc6bf79ca74c1cd2eea1cbbb3`).
Its background preflight records `blocked_model_contract` and performs no FEM
solve. Direct inspection of the saved AEDT project and RMxprt semantics found:

- Maxwell `ModelDepth='77.0793mm'`, not the frozen 120 mm;
- 36 conductors/slot, two layers, eight coils/phase, and one branch: 144
  series turns per phase, not 36;
- 40 active conductors/pole: 20 field turns/pole, not 80;
- `Bar`, `Bar_Separate1`, and `Bar_Separate2`, despite the no-damper contract.

The minimal RMxprt winding correction is 36 conductors/slot with four balanced
stator branches, plus 160 active conductors/pole for 80 field turns. The SynM3
template cannot natively set zero damper slots: it clamps zero to one, while
its generated end connection requires at least two bar objects. The `r3`
builder therefore uses the proven temporary three-bar conversion seed and is
designed to reclassify those sheets as rotor steel in the converted copy.

RMxprt analysis completed with the corrected turn settings and produced a
converted-design autosave. Later GUI recovery configured and independently
validated the corrected `r3` source. Its first write-once field-only anchor did
not produce a FEM row: the displaced solve rotated already clipped
quarter-sector sheets, causing Rotor/OuterRegion and stator/field intersections
and invalidating the periodic topology. That campaign is preserved and must
not be retried.

A new full-machine direct-geometry `r4` source then passed independent
inventory and AEDT `ValidateDesign` checks with 120 mm depth, 36 series turns
per phase, 80 field turns per pole, and no damper objects. The first frozen
field-only anchor still produced no FEM row because AEDT Student rejected the
initial mesh as larger than its licensed surface-element limit. The frozen
campaign, failed session, status/progress files, and their SHA-256 hashes are
preserved under
`out/eesm/task9_requalification_r4_attempt4_20260716/`. A reduced 90-degree
anti-periodic model is only a prospective new geometry/solver revision. It must
independently prove boundary orientation and explicit factor-four torque,
co-energy, and phase-flux scaling before any solve can count. No corrected FEM
result, replacement 64-point campaign, or Task 10 step is authorized.
