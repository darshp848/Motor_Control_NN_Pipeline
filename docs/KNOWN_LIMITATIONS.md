# Known limitations (IPM Stage 0)

**Stage 0 status: offline-frozen and audit-ready** — not FEM-audited and not deployment-ready FOC tables.

These are **documented bounds**, not silent bugs. The EESM branch must not inherit them as surprises.

## Fidelity

1. **AEDT Student mesh is coarse** (slider=1, MaxPasses=1 magnetostatic). Proof-of-concept map, not design-signoff FEM.
2. **Training current grid is much wider than control currents** (hundreds of amps vs ~6 A peak). Map step ≈ 7.7 A is coarser than the MTPA search domain near rated current.
3. **Training Id domain is only \([-300, 0]\)**. Positive Id (generation / some FW conventions) is **out of domain**.

## Validation history

4. **Pre-Stage-0 off-grid set mixed interpolation and extrapolation** (`ID_RANGE=(-300,300)` while training Id ≤ 0; 10/20 points had Id > 0). Mixed RMSE is **not** pure generalization. Use domain-stratified metrics.
5. **In-grid winner ≠ off-grid winner** historically (GP vs random forest on **mixed** off-grid). After Stage 0 domain split:
   - **In-domain interpolation** winner can be an MLP/GP (e.g. `mlp_small`) — this is the default promote policy.
   - **Mixed / extrapolation** winner remains closer to `random_forest`.
   - Re-run `mtpa_field_weakening.py` after any inference promote so the LUT matches the deployed model.

## Scheduler / LUT

6. **LUT is surrogate-selected until FEM audit is run**. `out/audit/lut_audit_commands.csv` freezes the prospective command list; FEM torque closure is optional/pending until AEDT audit.
7. **Many LUT rows are `infeasible`** at high speed / high torque on this machine+limits combo (~75% in the 2026-07-09 run). Check envelope before controller deployment.
8. **Near-rated LUT current vs RMxprt rated RMS** can disagree; treat as map/scale fidelity issue, not flash-ready FOC tables.

## Scaling

9. **`flux_scale ≈ 11.86` is large** — likely absorbs 2D depth / turn / unit conventions. Always load from `motor_params_clean.json`; never hardcode in new code.

## Process

10. **Full FEM re-export** (40×40, off-grid, LUT audit) requires GUI Run Script in AEDT; offline pipeline only uses CSVs under `data/`.
11. **No claim of measurement validation** — FEM-only chain so far.

When something fails on EESM, ask: *Is this EESM physics, or one of the items above?*
