# Flux extraction fix — diagnosis, new files, and what still needs a solve

**Date:** 2026-07-21
**Scope:** the RMxprt-derived `fractions=4` model (`EESM_2D_Qual`) that already solves cleanly.
**Not in scope:** the r5–r9 direct-build line. No file here touches it.

Evidence tags: **[V]** verified by reading files / computing on the Task 9 data · **[I]** inference · **[?]** requires an AEDT solve

---

## 1. Which stage produces the invalidities

You asked me to localise the fault before writing code. Here is what the existing data can and cannot settle.

### 1.1 It is not the Park transform, the angle, or the phase labelling **[V]**

`export_eesm_points.py` uses a standard amplitude-invariant Park pair (`dq_from_abc` line 119, `abc_from_dq` line 129) and passes the **same** angle at both call sites (line 231 currents out, line 415 flux in). Because `λd·iq − λq·id` is a cross product, it is invariant under any rotation applied consistently to both vectors — so a wrong reference angle cannot, by itself, produce the torque residual.

I then searched the full convention space on your 64 rows: all 6 phase permutations × all sign conventions, scored by zero-sequence ratio (which is angle-independent, so this search is exhaustive over that stage):

```
best achievable            0.3433   (six equivalent relabelings)
current export (0,1,2)+++  0.4042
worst                      1.8814
a correct winding          < 0.01
```

**No relabeling gets within a factor of 30 of correct.** The imbalance is upstream of anything the exporter does. **This is the key negative result: the fix cannot be a post-processing change.**

### 1.2 It is not a fixed gauge offset either **[V]**

Regressing λ₀ against the currents gives R² = 0.30 — neither a clean constant (which would indicate a vector-potential gauge artifact) nor cleanly excitation-driven. Mean λ₀ = −0.0099 Wb with σ = 0.0145 Wb; the variation exceeds the mean.

### 1.3 What the model actually is **[V]**

From RMxprt's own generated export (`Maxwl2DV.vbs`) and the solved mesh statistics:

- `OuterRegion` is an `RMxprt/Band` primitive with `Fractions = 4`; `SetSymmetryMultiplier "fractions"` at line 143 — a **one-pole 90° sector**
- confirmed independently by the mesh: 6 coils + 6 return coils, **1** field coil pair, **3** damper bars
- coil→winding→polarity (vbs 318–352):

| Winding | Sheets | Polarity |
|---|---|---|
| PhaseA | Coil_0, Coil_1, CoilRe_0, CoilRe_1 | **all Positive** |
| PhaseB | Coil_4, Coil_5, CoilRe_4, CoilRe_5 | **all Positive** |
| PhaseC | Coil_2, Coil_3, CoilRe_2, CoilRe_3 | **all Negative** |

Each phase has 4 sheets and equal conductor counts (`conds = 18`), so the winding is *numerically* balanced. But **within each phase, the go sheet and its return sheet carry the same assigned polarity.** There is no go/return sign pairing anywhere in the winding definition.

### 1.4 The mechanism **[I]**

Coil pitch is 6 and pole pitch is 24/4 = 6, so the winding is **full-pitch**: every coil spans exactly the 90° sector and its physical return conductor lives in the *adjacent* sector, where anti-periodicity inverts the field. RMxprt's convention is to give both sides the same nominal polarity and let the boundary condition supply the inversion.

That is self-consistent for the *current* distribution. It is delicate for **flux linkage**, because AEDT computes winding linkage as a signed sum of `∫A_z dS` over the assigned coil sheets. With no go/return sign pairing inside the winding, the sum is a half-loop quantity rather than a closed-loop one, and the arbitrary additive constant in `A_z` does not cancel the way it does for a properly paired coil. Phases A and B accumulate it with one sign and phase C with the other, which is exactly the shape of a non-zero `λa + λb + λc`.

**I could not confirm this from static files.** Whether AEDT internally accounts for the anti-periodic images when reporting `FluxLinkage` on a `fractions=4` model is not documented in anything in your repo, and it is the single fact that decides the fix. **[?]**

### 1.5 Does `fractions=4` scale flux linkage the way it scales torque?

**No — and this is the same question as the "144 vs 36 turns" ambiguity from the previous report.** **[I]**

- Torque: the sector produces ¼ of the machine torque → ×4, unconditionally.
- Flux linkage: depends on how the four sectors are *connected*.
  - **series** (1 parallel branch, 144 series turns/phase) → λ_full = 4 × λ_sector
  - **4 parallel branches** (36 series turns/phase) → λ_full = λ_sector

`build_canonical_eesm.py` line ~370 sets `"ParallelBranchesNum:=", "1"` — i.e. series — so ×4 would be the consistent choice, and the r2 freeze's demand for 36 turns implicitly assumes the parallel connection instead. **These two settings must be decided together; the current model has them decided inconsistently.** The new code makes the choice explicit rather than implicit.

---

## 2. New files

Nothing existing was modified. All four files are new, so you can diff and adopt deliberately.

### `eesm/src/validation/flux_invariants.py` — the validation gates

Four gates, each naming the physical law it enforces and reporting the measured quantity that violated it.

| Gate | Law | Scope |
|---|---|---|
| `gate_zero_sequence` | balanced winding: λa+λb+λc = 0 | **per-point** — safe inline, aborts at row 1 |
| `gate_field_couples_d_axis` | the field winding defines the d-axis: ∂λd/∂If > 0 | batch (≥8 pts) |
| `gate_salient_pole_saliency` | salient-pole rotor: Ld > Lq | batch (≥8 pts) |
| `gate_dq_torque_consistency` | dq torque identity = virtual-work torque | batch (≥8 pts) |

Two deliberate design choices:

- **Correlation is checked before magnitude** in the torque gate. High correlation with a wrong slope is a *fixable scaling error*; low correlation means the quantities aren't measuring the same thing and no rescaling helps. Reporting only a magnitude residual conflates them — which is precisely how a 42.47 N·m residual got read as a scaling problem when the underlying correlation was −0.04.
- **`inconclusive` is never treated as `pass`**, matching the existing qualification CLI's convention.

Verified against your actual Task 9 data — all four fire, and the zero-sequence gate rejects row 0: **[V]**

```
OVERALL: fail   points: 64
[FAIL] zero_sequence          60 of 64 points violate; first offender row 0
[FAIL] field_couples_d_axis   d(lambda_d)/d(If) = -4.3065e-04 Wb/A
[FAIL] salient_pole_saliency  Ld = 5.0978e-05 H, Lq = 1.6984e-04 H, Lq/Ld = 3.33
[FAIL] dq_torque_consistency  Pearson r = -0.0407; best-fit scale 0.6679 still leaves 42.475 N.m
```

Note: `eesm/src/validation/physics_invariants.py` already contains a `field_current_increases_lambda_d` check — but it is wired only to the synthetic map model and was never run against FEM output. Worth connecting.

### `eesm/aedt/diagnose_flux_convention.py` — evidence collection (run in AEDT)

Probe-first, deliberately makes no correction. Solves four cheap points on a **disposable copy** and records three *independent* flux measurements per point:

- **A** `FluxLinkage(PhaseX)` — what the campaign used
- **B** per-coil `FluxLinkage(<coil>)` — probed; the expression may not be valid, and the script records that rather than failing
- **C** `∫A_z dS` per sheet via the field calculator, plus each sheet's area — always available, and the only route that can be made gauge-independent

It also reads the coil→winding→polarity→conductor inventory, the symmetry multiplier, and the model depth **back from the live model** instead of trusting the build script.

Probe points are chosen to be physically decisive:

| Point | Purpose |
|---|---|
| `field_only` (0, 0, 2 A) | only the rotor field is energised, so λabc is a direct spatial sample of the rotor field axis — **the d-axis angle falls straight out of it, with no rotor rotation** (which matters: `build_canonical_eesm.py` deletes the `Band`, so the rotor cannot be rotated) |
| `d_probe_negative` (−50, 0, 0) | Ld |
| `q_probe_positive` (0, +50, 0) | Lq |
| `combined` (−40, 60, 4) | cross-check |

The all-zero origin is **excluded by default** — your qualification notes record that AEDT Student reproducibly exits inside `Analyze()` for that redundant solve. `PROBE_SOURCE_FREE_ORIGIN = True` re-enables it if you want to retest.

### `eesm/aedt/analyze_flux_convention.py` — offline verdict

Scores routes A/B/C against the balanced-winding law, and for whichever route passes, derives the true d-axis electrical angle from the `field_only` probe:

```powershell
.\.venv\Scripts\python.exe eesm/aedt/analyze_flux_convention.py `
    out/eesm/flux_convention_diagnostic/flux_convention_evidence.json `
    out/eesm/flux_convention_diagnostic/verdict.json
```

Route C implements the closed-loop form that cancels the gauge constant:

```
lambda_phase = sum over coils of  sign * N * depth * (A_z_go - A_z_return) / Area
```

If **no** route comes out balanced, the verdict says so explicitly and gives the next four checks in order — ending with the decisive control: solve the same operating point on a full 360° model with no periodic boundary. If the full model balances and the sector does not, the fault is the sector's periodic-image handling, and the practical fix is to extract flux from a full model even though torque can stay on the sector.

### `eesm/tests/test_flux_invariants.py` — unit tests

Covers each gate's pass and fail path, the `inconclusive`-is-not-`pass` rule, and a regression test asserting that a synthetic reconstruction of the Task 9 signature is rejected.

---

## 3. What I verified vs what needs a solve

**Verified [V]**

- No phase permutation or sign convention reduces the zero-sequence below 0.343 (correct: <0.01) — the fault is upstream of the transform
- The Park pair is standard and angle-consistent at both call sites
- λ₀ is not a fixed gauge offset (R² = 0.30 against currents)
- Every phase has 4 sheets and equal conductors, but **no go/return polarity pairing within any phase**
- Model is `fractions=4`, one pole, `SetSymmetryMultiplier "fractions"`, `ParallelBranchesNum = 1`
- All four new gates fire correctly on the real 64-row dataset

**Requires an AEDT solve — not resolved [?]**

1. **Whether AEDT includes the anti-periodic images in `FluxLinkage` on a `fractions=4` model.** This decides whether route A can be salvaged or route C is mandatory. → run `diagnose_flux_convention.py`, then `analyze_flux_convention.py`.
2. **The true d-axis electrical angle.** Currently assumed 180°; the field-only probe measures it directly.
3. **Whether per-coil `FluxLinkage(<coil>)` is a valid report expression** in AEDT 2025 R2 — the script probes rather than assumes.
4. **Whether the symmetry multiplier survived the `Setup_Qual` rebuild**, and so whether `T_FEM` is per-sector or full-machine. Circumstantially: max |T_FEM| ≈ 18 N·m × 4 = 72 N·m against the manifest's 80 N·m rated — suggestive of per-sector, but not proof.
5. ~~**The series-vs-parallel decision** (×4 or ×1 on flux linkage), which must be made jointly with the turns-per-phase question.~~ **RESOLVED 2026-07-21 — no solve can decide it.** Under the parallel reading terminal flux is ¼× but terminal current is 4×, so torque, power, and the field solution are identical either way; the dq torque identity is exactly invariant to the choice. It is machine-definition bookkeeping, and the frozen r2 contract is the only authority: **four parallel branches, 36 series turns/phase, flux multiplier ×1**. `build_canonical_eesm.py` now sets `ParallelBranchesNum = 4` for the stator phases (field stays 1), so commanded currents are terminal amps. Legacy probes (including the flux-convention diagnostic) were solved at 1 branch: their labelled currents are branch amps = terminal/4. See `flux_extraction_v2.py` NOTES 1 and 4.

**I am not claiming the invalidities are fixed.** They are localised, and the mechanism is identified with an explicit uncertainty. The diagnostic is built to close that gap in one AEDT session.

---

## 4. Suggested order

1. Renew the student licence — expires **2026-07-31**, and every step below needs a solve.
2. Copy the working project to a disposable name; run `diagnose_flux_convention.py` via Automation → Run Script.
3. Run `analyze_flux_convention.py`; read the verdict.
4. Decide series-vs-parallel and set the flux multiplier and turns consistently.
5. Re-export a **pilot block of ~8 points** with `gate_zero_sequence` inline, then run the batch gates.
6. Only if all four gates pass, re-run the 64-point campaign.
7. Keep the existing Task 9 dataset quarantined — the flux labels are wrong, not merely out of tolerance.
