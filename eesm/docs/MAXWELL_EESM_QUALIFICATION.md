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

## Manual sequence

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
3. In AEDT 2025 R2, run `eesm/aedt/export_eesm_points.py` manually through
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
4. The first run is a four-point 2x2 smoke only: `field_only`, `q_current`,
   `negative_d`, and `combined_rated`, all at `If=2 A`. Inspect the status JSON,
   progress CSV, and four ABC exports, then stop. Set `SMOKE_APPROVED=True` only
   after primary review; later fresh AEDT sessions resume the remaining three
   energized pilot points.
5. Preserve `eesm_qualification_progress.csv` as raw evidence. Its AEDT names
   and units are deliberately not canonicalized in place.
6. Run the offline normalizer, then qualifier:

   ```powershell
   python eesm/aedt/normalize_eesm_results.py eesm/aedt/eesm_qualification_progress.csv eesm/aedt/eesm_qualification_points.csv <canonical.csv>
   python eesm/aedt/qualify_eesm_project.py <canonical.csv> <qualification_report.json>
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
This unblocks the Task 9 software/campaign start but does not itself claim any
Task 9 campaign result or change the existing LUT audit thresholds.
