# Phase 0 torque convention

**Date:** 2026-08-12
**Status:** locked for the first FEMM baseline. Not a threshold freeze.

## Decisions

1. **F1 is closed** by the 360° model, not by 90° sector WST.
   Evidence: `out/eesm/femm_f1_360_20260812/f1_360.json`
   (285,339 elements, |T| asymmetry 0.168%, k = 1.0235 / 1.0255).
   Do not move the 3% number. Do not re-open F1 because a 90° WST
   pair still reads ~3%.

2. **Baseline geometry is the 90° sector** (`full_machine=False`).
   The map is `(id, iq, If) → (λd, λq)`. Sector fluxes already
   mirror to 0.03%. The 360° model is the instrument qualification,
   not the production mesh.

3. **Campaign torque is the dq identity**
   `T = 1.5 · p · (λd·iq − λq·id)` stored as `torque_identity_nm`
   and copied to `campaign_torque_nm`.
   `eesm.femm.campaign.campaign_torque_nm(row)` is the only allowed
   reader. It refuses a row that has WST but no identity.

4. **`torque_fem_nm` (sector WST) is diagnostic only.**
   Its ~0.04 N·m even residual is an antiperiodic-cut artifact
   (18× smaller on the 360° model). Do not fail a row, freeze a
   threshold, or audit the scheduler against it.

5. **New campaign root.** Do not write into
   `out/eesm/task9_baseline/`. Convert Task 9 points with
   `eesm.femm.points` into a fresh directory.

6. **64-point live baseline exists.** Evidence:
   `out/eesm/femm_baseline_64_20260812/` (64/64 converged on
   `femm_4.2`, 73,904 elements, schema-valid,
   `campaign_sanity.json`).

7. **128/256 identities are frozen** as the executable equal-budget
   matrix, not as a scaled Task 9 campaign. Evidence:
   `out/eesm/femm_equal_budget_points_20260813/`
   (1760 identities, 1759 FEMM-solvable, origin excluded;
   SHA-256 `b85ea01c84267500d3270337e60dad42f7367dd9faf0326e586ceee895adfe01`).
   Task 9 `40/12/8/4` is untouched.

8. **Equal-budget live campaign exists.** Evidence:
   `out/eesm/femm_equal_budget_20260813/` (1759/1759 converged on
   `femm_4.2`, 73,904 elements, schema-valid,
   `campaign_sanity.json`).

9. **FD Hessian anchors exist** (validation truth, not a gate):
   `out/eesm/femm_fd_anchors_20260813/`. Still blocked: threshold
   freeze, family comparison, promotion, LUT, training.

10. **Threshold-freeze method is locked.** Proposal (not a manifest
    write): `out/eesm/threshold_proposal_20260813.json` and
    `eesm/docs/THRESHOLD_FREEZE_METHOD.md`. Manifest
    `gates.status` is **frozen** to those numbers (2026-08-13).

11. **Equal-budget fit, promotion, and prospective audit are complete.**
    Study: `out/eesm/equal_budget_femm_20260813/` (36/36). Close:
    `out/eesm/phase0_close_20260813/`. Promoted
    `latin_hypercube|256|rbf_or_gp`. Scheduler-audit opened only after
    promotion and passed. Result bundle:
    `out/eesm/phase0_close_20260813/result_bundle.json`.

Conventions appendix (3/2 field reciprocity, no v2 model):
`eesm/docs/DQ_CONVENTIONS.md`. FD Hessian anchors are specified but
not run: `eesm/docs/FD_HESSIAN_ANCHORS.md`.

Executable pin: `eesm/tests/test_femm_campaign.py::test_campaign_torque_is_the_identity_not_sector_wst`.
