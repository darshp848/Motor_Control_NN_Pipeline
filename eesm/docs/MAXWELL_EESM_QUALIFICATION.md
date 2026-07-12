# Maxwell EESM qualification gate

This gate is prospective. No Maxwell pilot has been run and no project is
qualified by these files alone. The eight-point pilot is assigned the frozen
`reference` role and must remain separate from training, selection, and the
current LUT `scheduler_audit` workflow.

## Manual sequence

1. Review and record the authoritative project, design, setup, local variable
   names, Park convention, current bases, field excitation, pole-pair count,
   rotor-position convention, mesh evidence, and output-variable definitions.
2. Update only the reviewed constants and current bindings in
   `eesm/aedt/export_eesm_points.py`. In AEDT 2025 R2, run it manually through
   **Automation -> Run Script**. The script is resumable and records one row per
   attempted solve, including failures; it does not launch or attach AEDT. Flux
   is exported through the proven PhaseA/B/C flux-linkage data table, checked
   for a nonempty file, then converted to dq. It aborts after a solve failure.
   Before any solve, configure a positive integer pole-pair count, measured
   mesh-element count, measured adaptive-pass count, and the reviewed torque
   output-variable name. The script refuses to solve while any is undeclared.
   It also refuses to resume a progress file containing any failed row.
3. The first run is a four-point 2x2 smoke only: `field_only`, `q_current`,
   `negative_d`, and `combined_rated`, all at `If=2 A`. Inspect the status JSON,
   progress CSV, and four ABC exports, then stop. Set `SMOKE_APPROVED=True` only
   after primary review; a later run resumes into the remaining pilot points.
4. Preserve `eesm_qualification_progress.csv` as raw evidence. Its AEDT names
   and units are deliberately not canonicalized in place.
5. Run the offline normalizer, then qualifier:

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
