# Physics-gate threshold-freeze method (Paper 2)

**Status:** method locked. Proposal numbers live in
`out/eesm/physics_threshold_proposal_20260813.json` and in the
`physics_gates` block of `eesm/configs/eesm_experiment_manifest_v2_3.json`.
**Date:** 2026-08-13
**Does not:** edit Phase 0 gates, fit a competing family, open
`selection` or `scheduler_audit`, or re-rank Phase 1.

## Contamination disclosure

Phase 1 already published family-level reciprocity and \(L_\mathrm{diff}\)
tables in `eesm/docs/PHASE1_SCIENCE.md`. Those numbers were visible when
this freeze was written. They are **not** an input to the thresholds.

The instrument is the same non-competing IDW used for Paper 1, applied
for the first time to reciprocity and incremental inductance. That residual
had not been computed before this freeze. The family tables therefore
cannot have selected the instrument or the numbers.

This is predeclaration of a new gate set, not preregistration of the
Phase 1 diagnostic.

## Why a separate gate set

Paper 1 showed that the eight interpolant-derived flux/torque/voltage
gates did not discriminate. Reciprocity and \(L_\mathrm{diff}\) did, but
only as ungated diagnostics. Promoting on a metric chosen after seeing
that it favours the energy-gradient net would be outcome-dependent
selection. The clean fix is to freeze thresholds from an instrument that
is not a competitor, using only roles that Paper 1 already allowed.

Phase 0's eight gates stay frozen and unchanged.

## Roles

Allowed to set numbers:

- the three frozen 64-point training designs
  (`tensor_grid_64`, `random_64`, `latin_hypercube_64`)
- other `train` rows as IDW holdout
- the eight FD Hessian anchors (measurement floor and \(L_\mathrm{diff}\)
  truth), which were collected before any competing-family fit

Forbidden:

- `selection`
- `scheduler_audit`
- every competing family, including `energy_gradient_net` and `pwa`

## Instrument

Inverse-distance weighting, power 2, on currents normalized by the map
box. Outputs are \((\lambda_d,\lambda_q,\lambda_{f,\mathrm{terminal}})\).
This interpolant is not a surrogate family.

For each 64-point design \(D\):

1. Fit IDW on the design points that have FEMM truth.
2. Reciprocity: evaluate RMS \(|R_{dq}|\), \(|R_{fd}|\), \(|R_{fq}|\) on
   **train holdout** rows that have \(\pm h\) room in the domain, with
   \(h=(1,1,0.2)\) A (the FD-anchor steps).
3. \(L_\mathrm{diff}\): evaluate the IDW Jacobian at the eight FD-anchor
   centres against the measured terminal Jacobian. Record Frobenius
   relative RMSE and off-diagonal mean relative RMSE.

```text
raw[g]       = max(instrument_D[g] for D in {tensor, random, LHS}_64)
threshold[g] = max(raw[g], floor[g])
```

## Floors

Floors are measurement slack, not family-tuned bars.

| Gate | Floor | Basis |
|---|---|---|
| `R_dq_rms_h` | FEM \(R_{dq}\) floor from the anchors | cannot require beating the instrument |
| `R_fd_rms_h` | FEM \(R_{fd}\) floor | same |
| `R_fq_rms_h` | FEM \(R_{fq}\) floor | same |
| `ldiff_frobenius_rel` | 0.05 | declared 5% relative slack |
| `ldiff_offdiag_rel` | 0.05 | declared 5% relative slack |

Using the **worst** of the three 64-point IDWs is the same permissive
choice as Paper 1. If the resulting physics gates fail to discriminate,
that is a reportable result, not a reason to retune after seeing families.

`R_fd_naive` is recorded as a tripwire. It is not a gate.

## Executable pin

```text
python -m eesm.run_physics_threshold_proposal
```

writes the proposal JSON and does not edit Phase 0 files. Tests:
`eesm/tests/test_physics_threshold_method.py`.

## Instrument outcome (IDW, not families)

On the three 64-point designs the worst-IDW reciprocity RMS values are
about \(10^{-3}\) H (\(R_{dq}\)) and \(10^{-2}\) H (\(R_{fd}\), \(R_{fq}\)).
The IDW Jacobian is a poor incremental-inductance model: off-diagonal
relative error is order 1–7, so the \(L_\mathrm{diff}\) gates are
permissive by construction. That is a property of the instrument, recorded
after the proposal was computed, not a reason to retune.
