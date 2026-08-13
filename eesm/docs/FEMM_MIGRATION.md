# FEMM migration

## Current status — 2026-08-12

This block supersedes conflicting historical status text below. The live branch
is `femm-migration` at `2d6304f` plus uncommitted FEMM-path work (mesh control,
360° builder, Phase 0 torque convention). Real FEMM solves have run. The model
is rebuilt from the frozen spec with the pinned `rmxprt-steel_1008-r1` BH table.

**F1 is closed on the 360° model.** Evidence:
`out/eesm/femm_f1_360_20260812/f1_360.json` — 285,339 elements, |T| asymmetry
0.168%, k = 1.0235 / 1.0255, field λq = −3.3e-6 Wb. The 90° sector's ~3% WST
mirror miss is an antiperiodic-cut artifact (T_even −0.043 → −0.002 N·m).

**Phase 0 torque convention** is `eesm/docs/PHASE0_TORQUE_CONVENTION.md`:
baseline stays on the 90° sector; campaign torque is the dq identity;
`torque_fem_nm` is diagnostic only.

**The 64-point live baseline exists.** Evidence:
`out/eesm/femm_baseline_64_20260812/` — 64/64 converged, backend
`femm_4.2`, 73,904 elements, Task 9 identities converted not rewritten,
`campaign_torque_nm` = identity. Sanity:
`out/eesm/femm_baseline_64_20260812/campaign_sanity.json`.

**128/256 identities are frozen** at
`out/eesm/femm_equal_budget_points_20260813/`. These are the
manifest equal-budget designs (3 strategies × {64,128,256} train,
shared 256 selection, sealed 256 scheduler_audit). They are not a
Task 9 expansion. Origin `(0,0,0)` A is analytic and is not in the
FEMM points file. Threshold freeze, fitting, and the 1759-point
FEMM solve is complete at `out/eesm/femm_equal_budget_20260813/`
(1759/1759, `campaign_sanity.json`). Thresholds are **frozen** in
the manifest from `threshold_proposal_20260813.json`. The 36-cell
FEMM fit, promotion (`latin_hypercube|256|rbf_or_gp`), and
post-promotion scheduler-audit are in
`out/eesm/phase0_close_20260813/`.

Earlier 90° WST diagnostics (r2 refine 3.19%, line integral k≈−0.78, type-7
refusal) are preserved under `out/eesm/femm_f1_*` and
`eesm/docs/TORQUE_INSTRUMENT_REVIEW.md`. They do not reopen F1.

The remainder of this document is retained as migration history. Where it says
that no solve has run, that F1 is open, or that spec defects later closed by
`2d6304f` remain, this current-status block controls.

Authority for the scope, blocking inputs, and Windows confirmation checklist of
`eesm/femm/`. Cited by `eesm/femm/__init__.py`, `runtime.py`, `config.py`,
`mock_femm.py`, and both FEMM test files. If this document and a docstring
disagree, the code is the claim and this document is the contract it is
measured against.

Status: **plumbing qualified offline, no solve ever performed.** No FEM row, no
surrogate, no LUT, and no Task 10 authorization is claimed here.

## Why the Maxwell path was replaced

AEDT Student caps 2D magnetostatic solutions at roughly 2000 surface elements,
and a refined 2517-element mesh was rejected outright. Torque could therefore
never be made accurate. The decisive evidence is recorded in
`eesm/aedt/flux_extraction_v2.py` NOTE 4: a pure-q / negative-q mirror pair
whose flux linkages agree to 0.01% produced `Torque_FEM` values differing by
27.5%, and zero-torque points reported 0.004-0.005 N.m of spurious torque.
That is solver noise, not physics. It is also the direct cause of the Task 9
result in which 59 of 64 rows exceed the frozen 1.1 N.m torque-closure limit,
with a maximum residual of 42.474642129016004 N.m.

FEMM 4.2 (build 21Apr2019) with pyFEMM 0.1.3 removes the element cap and adds
antiperiodic boundaries, circuit flux linkage as a direct output, and a
sliding-band rotor-motion model.

The AEDT path under `eesm/aedt/` is untouched and remains the parallel history.
Preserved AEDT evidence is never rewritten, reinterpreted, or deleted because
of anything in this document.

## Scope guard

`eesm/femm/` is qualified for **convention and plumbing only**: column
contracts, current conventions, dq arithmetic, resume and refusal behaviour,
schema validation, and provenance. It is **not** authorised for dataset
generation, canonical normalization, surrogate fitting, promotion, LUT audit,
training, or any published result.

Two physical inputs are missing, and neither can be resolved on a machine
without FEMM or without the real machine data.

### Blocking input 1: the real BH curve

`materials.steel_material` is a **documented placeholder** (M-19 as a
stand-in). Any operating point the manifest would label `saturation` is
physically meaningless until the real curve replaces it. A campaign run with
the placeholder must not be normalized or fitted, whatever its residuals look
like.

### Blocking input 2: the airgap

`geometry.airgap_mm` is 0.6 mm, derived as `(110 - 108.8)/2` from the RMxprt
export. The same export emitted `DiaGap` as **110, 108.8 and 109.4 mm** across
different VBS blocks. The 109.4 mm reading would give a 0.3 mm airgap — **a
factor of two on the dominant reluctance of the machine**. Confirm the true
value before any production run. `geometry.stator_inner_diameter_mm` and
`geometry.rotor_outer_diameter_mm` are unverified for the same reason.

### Also unconfirmed: the d-axis angle

`extraction.d_axis_electrical_deg` comes from the construction of
`geometry.build_sector()` and is deliberately **not** the AEDT model's
330.01 deg. It needs a field-only FEMM probe to confirm: energize the field
winding alone, and check that the flux linkage lands on +d with q at zero.

## Unverified constants

`unverified=True` in `config.PROVENANCE` means the number is a placeholder or a
transcription whose ground truth has not been confirmed. **It is a finding, not
a blank that was filled in.**

24 of the 72 config fields are currently flagged, in five groups:

| Section | Count | What it means |
|---|---|---|
| `geometry` | 3 | The airgap ambiguity above. |
| `materials` | 5 | Placeholder steel; library names not read back; RMxprt lamination defaults not measured. |
| `extraction` | 1 | The d-axis angle probe above. |
| `domain` | 6 | `parameter_status = synthetic_baseline` in the manifest — placeholders, not measurements. Nothing derived from them is validated. |
| `api` | 9 | Every FEMM API constant. Recalled from the manual, never read back. See below. |

The list is generated, never hand-maintained. To reproduce it:

```
.venv/bin/python -c "from eesm.femm import config; \
  [print(k) for k in sorted(config.unverified_fields())]"
```

Every campaign status JSON embeds this list under `config_provenance.unverified`,
so a run always carries its own caveats. `test_femm_geometry.py` fails if any
config field has no provenance entry at all.

## What the mock can and cannot prove

`mock_femm.MockFemm` records every API call and returns analytically exact flux
linkages for a linear salient machine. That makes the geometry assertable
structurally and the dq/torque arithmetic assertable to floating-point
precision, with no FEMM installed.

It proves **nothing** about:

- whether the geometry is the real machine — the sector is reconstructed from
  RMxprt scalars with no DXF to check against;
- whether any `FemmApiConfig` value is correct — **the mock accepts whatever
  config says**, so a wrong boundary code or block-integral type passes every
  offline test and can only be caught on Windows;
- saturation, iron loss, or anything else the placeholder BH curve governs;
- the airgap.

A campaign that passes every offline test has still never touched a solver.

## Windows confirmation checklist

Work through this on the first run against a live FEMM 4.2. Nothing below has
ever been executed.

### 1. Confirm the four highest-risk constants first

These change results silently rather than raising, so they come before anything
else:

| Constant | Current value | Why it is dangerous |
|---|---|---|
| `api.boundary_format_antiperiodic` | `5` | If the enum is wrong, the sector gets the wrong symmetry and every flux linkage is wrong while the solve still succeeds. |
| `api.block_integral_torque` | `22` | Wrong integral type returns some other quantity as "torque". |
| `api.circuit_type_series` | — | Wrong circuit type breaks the turns/branch convention. |
| `api.problem_type` / `api.problem_units` | `planar` / `millimeters` | Wrong units silently rescale the whole geometry. |

### 2. Confirm the call surface

`runtime.FEMM_CALL_SURFACE` is the complete list of 26 calls this package
makes. It is a **diagnostic, not a gate** — the list is itself unverified, so
`detect_femm()` reports which calls a live pyFEMM is missing but never refuses
on that basis. A wrong name here must not be able to block a real run.

```
openfemm, newdocument, closefemm, mi_probdef, mi_getmaterial, mi_addmaterial,
mi_addcircprop, mi_addboundprop, mi_drawline, mi_drawarc, mi_addblocklabel,
mi_selectlabel, mi_setblockprop, mi_selectsegment, mi_setsegmentprop,
mi_clearselected, mi_setcurrent, mi_saveas, mi_analyze, mi_loadsolution,
mo_getcircuitproperties, mo_groupselectblock, mo_blockintegral, mo_clearblock,
mo_numelements, mo_close
```

`runtime.PYFEMM_SENTINELS` (`openfemm`, `mi_probdef`, `mi_analyze`) is the
gate: a module named `femm` that lacks these is not pyFEMM, however it reached
`sys.path`.

Run `python eesm/run_femm_campaign.py --check` and read `missing_api`. An empty
list means every call this package makes exists in the installed pyFEMM.

### 3. Confirm the d-axis angle

Field-only probe, as described above, before any multi-point campaign.

### 4. Then, and only then, a bounded campaign

One point first. Compare `torque_fem_nm` against `torque_identity_nm` in the
result row. The AEDT path failed exactly here; a FEMM run that reproduces a
large residual has not fixed the problem, it has relocated it.

## Hazard: `eesm/femm` shadows pyFEMM on `sys.path`

Python puts a script's own directory at the front of `sys.path`. Any script
under `eesm/` — including `eesm/run_femm_campaign.py` — therefore makes
`import femm` resolve to **this repository's `eesm/femm/` package**, not
pyFEMM. Installing real pyFEMM on the Windows machine does not remove the
collision; the local package still wins.

`detect_femm()` catches this and names it:

```
pyfemm not importable (a module named 'femm' imported from
.../eesm/femm/__init__.py, which is this package itself, not pyFEMM);
this repository's own eesm/femm package ... is shadowing pyFEMM on sys.path
```

If `--check` reports `shadowed_by`, the installed pyFEMM is **not** what would
be driven. Run the campaign from the repository root rather than from inside
`eesm/`, or import the runner as a module, and re-check before solving.

## Running it

### Invoke it as a MODULE, from the repo root

```
python -m eesm.run_femm_campaign --check
python -m eesm.run_femm_campaign \
    --out out/eesm/femm_rehearsal \
    --points out/eesm/task9_baseline/frozen_points.csv \
    --mock
```

**Not** `python eesm/run_femm_campaign.py`. Python front-loads a script's own
directory onto `sys.path`, so running it by path puts `eesm/` first and
`import femm` resolves to this repository's own `eesm/femm/` package instead of
pyFEMM. The probe detects that and reports `femm_importable: false` with a
`shadowed_by` field naming the culprit — correct behaviour, but it means the
runner is unreachable by that invocation even when pyFEMM is correctly
installed. Running as a module puts the repo root on `sys.path` instead, and
`import femm` finds site-packages.

Confirmed 2026-08-11 on a machine with FEMM 4.2 and pyfemm 0.1.3: by path,
`femm_importable: false`; as a module, `femm_importable: true`,
`missing_api: []`.

The mock is **opt-in**. Without `--mock` the runner resolves a real handle and
fails loudly on a machine without FEMM; it never falls back silently. A mock
run prints a banner saying its numbers are not evidence, and its status JSON
records `solver_backend: mock_femm` and `real_solve_performed: false`.

### Evidence discipline the runner enforces

- `guard_campaign_root()` refuses any `--out` directory holding
  `campaign_freeze.json`, `canonical_campaign.csv`, `campaign_report.json`,
  `raw/`, or `failed_runs/`. A new campaign is a new directory, never an
  addition to someone else's freeze. Pointing `--out` at
  `out/eesm/task9_baseline/` is refused.
- `points.adapt_points_file()` refuses to write into its source's own
  directory, and refuses to overwrite an existing destination.
- The frozen points file is hashed; a changed file aborts a resume.
- Rows are appended, never rewritten; a completed point is skipped without the
  solver being called; a row is validated against
  `eesm/schemas/eesm_point.schema.json` **before** it is written; a failed
  solve stops the run and is never recorded as data.

All of the above are asserted in `eesm/tests/test_femm_campaign.py`.

### Points file dialects

The Task 9 export spells its columns the AEDT way (`PointName`, `Id [A]`,
`Iq [A]`, `If [A]`); `campaign.read_points()` requires `point_name`, `id_a`,
`iq_a`, `if_a` and refuses the AEDT spelling. This is deliberate — a reader
that accepts two dialects cannot tell an operator which one it just read.
`eesm/femm/points.py` converts explicitly, copies `point_id`, `role` and
`region` verbatim, and writes a `frozen_points.csv.provenance.json` sidecar
recording the source path, source SHA-256, the exact mapping, and the dropped
columns.

## Gate status

Updated 2026-08-12 after the first real solves.

| Gate | State |
|---|---|
| Offline software and schema validation | **passed** |
| Any FEMM solve | **passed** — converging to 500k+ elements, 113x the AEDT Student cap |
| FEMM API constants | **passed** — `missing_api: []` against pyfemm 0.1.3; the 4 silent-failure enums verified against `C:\femm42\bin\manual.pdf` |
| d-axis electrical angle | **passed** — derived as 150.0° from the winding map, FEMM measures 149.999° |
| Airgap dimension | **passed** — 0.6 mm. Bore 110.0 and rotor OD 108.8 read directly from `eesm_pilot_source_01.aedt`, matching the frozen spec |
| Model depth | **passed** — 120 mm contract stack (was RMxprt's 77.0793 mm, a documented defect) |
| Torque instrument (F1) | **passed** — mirror \|T\| asymmetry 1.31% against the 3% gate; closure k = 1.044 at peak torque, inside [0.90, 1.10] |
| **Pole arc** | **FAILS SPEC** — drawn 48.86° (0.543 ratio) against the frozen spec's 58.5° (0.65). See below |
| **Rotor hub / pole body split** | **FAILS SPEC** — hub outer radius 24.4 mm against the spec's 34.0 |
| **Lamination material** | **FAILS SPEC** — `M-19 Steel` in use where §5 names `steel_1008` and forbids substitution |
| Exterior solution region | **deviates** — Dirichlet at 90 mm against the spec's 135 mm |
| Canonical normalization, fitting, promotion, LUT audit, Task 10 | **blocked** on the four above |

The remaining blocks are **spec-conformance defects, not missing measurements**.
`GeometryConfig` was transcribed from RMxprt scalars rather than from
`docs/superpowers/specs/2026-07-12-canonical-academic-eesm-geometry-design.md`,
and the RMxprt implementation drifted from that spec in at least six places —
model depth and field turns were the first two found, the four above are the
rest.

Numerical thresholds remain `baseline_required`. Nothing in this migration
changes that.
