# Maxwell EESM qualification gate

This gate is prospective. No Maxwell pilot has been run and no project is
qualified by these files alone. The eight-point pilot is assigned the frozen
`reference` role and must remain separate from training, selection, and the
current LUT `scheduler_audit` workflow.

## Manual sequence

1. Open `aedt_mcp/tmp/aedt_projects/eesm_qual/eesm_qual.aedt` in AEDT Student
   2025 R2. Run `eesm/aedt/build_canonical_eesm.py` through **Automation ->
   Run Script**. It rebuilds only `EESM_2D_Qual`, writes
   `eesm/aedt/eesm_model_build_status.json`, validates and saves the project,
   and never starts a solve. Stop unless status is `built` and
   `solve_attempted` is `false`.
2. Review and record the authoritative project, design, setup, local variable
   names, Park convention, current bases, field excitation, pole-pair count,
   rotor-position convention, mesh evidence, and output-variable definitions.
3. Update only the reviewed constants and current bindings in
   `eesm/aedt/export_eesm_points.py`. In AEDT 2025 R2, run it manually through
   **Automation -> Run Script**. The script is resumable and records one row per
   attempted solve, including failures; it does not launch or attach AEDT. Flux
   is exported through the proven PhaseA/B/C flux-linkage data table, checked
   for a nonempty file, then converted to dq. It aborts after a solve failure.
   Before any solve, configure the positive integer pole-pair count and reviewed
   torque output-variable name. After each solve, export convergence and mesh
   statistics and derive the actual triangle and adaptive-pass counts from
   those raw files. The script refuses rows with missing solver evidence.
   It also refuses to resume a progress file containing any failed row.
4. The first run is a four-point 2x2 smoke only: `field_only`, `q_current`,
   `negative_d`, and `combined_rated`, all at `If=2 A`. Inspect the status JSON,
   progress CSV, and four ABC exports, then stop. Set `SMOKE_APPROVED=True` only
   after primary review; a later run resumes into the remaining pilot points.
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

Each qualification check reports `pass`, `fail`, or `inconclusive` for
excitation, dq signs, units, pole pairs, flux channels, convergence, and torque
closure. An inconclusive result blocks qualification; it is not a soft pass.
No numerical torque tolerance is invented here. Task 9 must document the
translation between FEM torque and the controller-facing torque calculation,
establish an evidence-based tolerance, and resolve closure. The existing LUT
audit and its torque definition remain unchanged.
