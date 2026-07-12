# Prospective EESM Maxwell handoff

This boundary is manual and prospective. The offline pipeline freezes LUT audit
commands; it does not launch AEDT or claim that a Maxwell campaign has run.

## Qualification and export

1. Qualify the canonical EESM geometry, materials, mesh, solver revision, Park
   convention, current bases, rotor angle, and pole-pair count before a sweep.
2. Copy only rows with `needs_fem=true` from the frozen audit-command CSV into
   the Maxwell workflow. Do not refit or change commands after seeing results.
3. Export the canonical columns required by `eesm_point.schema.json`, plus
   `torque_nm` and `pole_pairs` when available.
4. Set `role` to `scheduler_audit`, preserve `provenance_id`, and use explicit
   `solver_status` and `converged` values for every requested point.
5. Copy the qualified CSV to the canonical FEM-data location declared for the
   campaign, then run the offline audit join.

The join retains every frozen command and assigns `audited`, `missing_fem`,
`fem_failed`, or `not_auditable_infeasible`. It recomputes torque and stator
voltage with `pipeline.physics`. Scheduler-audit results affect release
acceptance only and must not influence fitting, budgets, promotion, or refits.
