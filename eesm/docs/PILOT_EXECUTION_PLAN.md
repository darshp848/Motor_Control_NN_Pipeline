# EESM pilot execution plan — handoff for GLM 5.2

**Date:** 2026-07-21. **Deadline pressure:** AEDT Student licence expires **2026-07-31**; every phase below except Phase 2 needs a live solve, so complete this in one pass.

## Context you must load first (read, do not skim)

- [ ] `eesm/aedt/flux_extraction_v2.py` — the confirmed extraction. **NOTES 1–4 at the bottom are binding.**
- [ ] `eesm/docs/FLUX_EXTRACTION_FIX.md` — mechanism history, including the superseded go/return-differencing hypothesis. Do not reintroduce it.
- [ ] `out/eesm/flux_convention_diagnostic/verdict.json` — measured constants and route ranking.
- [ ] `eesm/aedt/diagnose_flux_convention.py` — working example of an IronPython solve/probe script against this model.

### Settled facts — do not re-litigate

| Fact | Value | Source |
|---|---|---|
| Extraction route | **C (A_z recomputation), same-sign coils** | verdict.json; route A imbalance 0.39 |
| `FluxLinkage(PhaseX)` | unusable for labels | diagnostic |
| `FluxLinkage(<coil>)` | not a valid expression | route B returned nothing |
| d-axis electrical angle | **330.01°** (needs one confirming point, Phase 4) | field-only probe |
| Winding connection | **4 parallel branches, 36 series turns/phase, flux multiplier ×1** | r2 contract; bookkeeping decision, provably not measurable |
| Torque | multiplies by FRACTIONS = 4, unconditionally | flux_extraction_v2 |
| Legacy probe currents | **branch amps = terminal/4** (solved at 1 branch) | NOTES 1 |

### Hard constraints

- IronPython 2.7 inside AEDT: no f-strings, no `open(..., newline="")` (use `csv.writer(..., lineterminator="\n")`), no `math.isfinite`.
- AEDT 2025 R2 Student: surface-element limit; `GetSymmetryMultiplier`/`GetDesignSettings` do not exist on these objects.
- Delete stale `.aedt.lock` (dead PID) after any hard kill. Open the project in the GUI before Run Script.
- All runner `.ps1` files must be Windows PowerShell 5.1-compatible; manifest bookkeeping must be non-fatal (pattern already in `run_flux_convention_diagnostic.ps1` — copy it, do not invent).
- **Never loosen a gate to force a pass.** Report failures as failures.

---

## Phase 1 — make the project match the contract (GUI + script)

- [ ] 1.1 Copy the working project to a disposable name before touching anything.
- [ ] 1.2 Apply `ParallelBranchesNum = 4` to PhaseA/B/C windings (Field stays 1). The fix exists in `build_canonical_eesm.py` (~line 355) but the **solved project still has 1** — rebuild or edit the winding in the open project.
- [ ] 1.3 Write a preflight check into the export script: read back the three phase windings and **abort with a clear message if any `ParallelBranchesNum != 4`**. A run against a 1-branch project must be impossible, not merely discouraged.
- [ ] 1.4 Verify sheet inventory still matches `COIL_MAP` in `flux_extraction_v2.py` (12 coil sheets, same names). Abort if not.

**Exit gate:** preflight passes; a deliberately broken copy (PB=1) is rejected by 1.3.

## Phase 2 — rewrite the exporter (offline, no licence needed)

Target: `eesm/aedt/export_eesm_points.py` (475 lines). It currently uses route A (`FluxLinkage(PhaseX)`), `ROTOR_POSITION_DEG = 180.0`, and legacy-frame current injection — all three disproven.

- [ ] 2.1 Import constants and functions from `flux_extraction_v2.py` (it is IronPython-safe by design): `D_AXIS_ELECTRICAL_DEG`, `CONDUCTORS_PER_SHEET`, `MODEL_DEPTH_M`, `FRACTIONS`, `COIL_MAP`, `zero_sequence_ratio`. No copy-pasted duplicates — one source of truth.
- [ ] 2.2 Replace flux readout with route C: per-sheet `∫A_z dS / S` reports, signed per `COIL_MAP` (same-sign; **no go/return differencing**), × conductors × depth. Flux multiplier ×1 (terminal flux).
- [ ] 2.3 Inject currents in the **330.01° frame** and treat commanded (id, iq) as **terminal amps** (PB=4 divides by 4 internally). Field current unchanged.
- [ ] 2.4 Run `zero_sequence_ratio` inline per point; write it into every CSV row. Rows with ratio ≥ 0.05 are labelled `suspect`, not dropped and not silently accepted.
- [ ] 2.5 Also record per point: `Torque_FEM` (sector value), mesh element count, convergence, provenance id, and the exact injected phase currents.
- [ ] 2.6 Keep every schema column the r2 point contract requires (`eesm/schemas/eesm_point.schema.json`); validate one sample row offline against it.

**Exit gate:** offline dry-parse of the script under CPython (`python -m py_compile`) plus a mock-object unit run of the abc/dq round trip: `dq→abc→dq` identity to 1e-12 at θ = 330.01°.

## Phase 3 — define the pilot block (offline)

- [ ] 3.1 Eight points, all **terminal** amps, inside the exporter domain — nothing near the legacy 200 A-terminal excursions. Include: one field-only at a **different If than 2 A** (confirms the 330.01° angle, NOTES 2), one pure-d, one pure-q, one combined at modest load, one saturation-neighbourhood point, and the rated-ish point.
- [ ] 3.2 Densify the mesh as far as the Student surface-element limit allows; record the achieved element count. The 0.0797 q-probe caveat and the failed torque closure are both plausibly mesh artifacts — this run decides.
- [ ] 3.3 Freeze the pilot CSV + SHA-256 before solving.

## Phase 4 — solve and gate (licence required)

- [ ] 4.1 Run the pilot via the runner pattern (`run_flux_convention_diagnostic.ps1` as template; 5.1-safe, non-fatal manifest).
- [ ] 4.2 Gate: zero-sequence < 0.05 on all points (route C). If the q-type point still sits near 0.08 at the denser mesh, that is a real finding — report it, do not tune.
- [ ] 4.3 Gate: **torque closure** — `1.5 · p · FRACTIONS · (λd·iq_branch − λq·id_branch)` vs `Torque_FEM × FRACTIONS`, currents and flux in the same 330.01° frame. Legacy residuals were +11% to +185% (NOTES 4); this run must explain or eliminate them. Target < 10% at unsaturated points; report per-point.
- [ ] 4.4 Confirm d-axis angle from the second field-only point agrees with 330.01° within ~1°; then freeze `D_AXIS_ELECTRICAL_DEG`.
- [ ] 4.5 Re-derive Ld, Lq from clean same-frame probes (replaces the mixed-frame 3.58/1.89 mH numbers, NOTES 3). Check Ld > Lq > 0.
- [ ] 4.6 Verify ∂λd/∂If > 0 at the new If point.

**Exit gate:** all of 4.2–4.6 pass, or each failure has a written cause hypothesis and the constants stay unfrozen.

## Phase 5 — lock in

- [ ] 5.1 Update `flux_extraction_v2.py` NOTES: mark 2, 3, 4 resolved (or amended) with measured values.
- [ ] 5.2 Update `FLUX_EXTRACTION_FIX.md` §"Requires an AEDT solve" with outcomes.
- [ ] 5.3 Hash and archive the pilot evidence under `out/eesm/` (runner does this; verify the manifest is non-empty this time).
- [ ] 5.4 Only if all gates pass: proceed to the 64-point campaign re-export. The old Task 9 dataset stays quarantined — its flux labels are wrong, not out-of-tolerance.

---

## Forbidden moves

1. Loosening the 0.05 zero-sequence gate or the torque-closure target to force a pass.
2. Reintroducing go/return differencing (disproven by solve) or ×4 flux scaling (contradicts the r2 contract).
3. Reading `FluxLinkage(PhaseX)` for labels.
4. Mixing legacy branch-amp data with new terminal-amp data without the ×4 conversion, in either direction.
5. Editing thresholds, seeds, or the r2 contract itself — those are frozen foundry configuration.
6. Claiming controller readiness, promotion, or validation from this pilot. It qualifies extraction conventions, nothing more.
