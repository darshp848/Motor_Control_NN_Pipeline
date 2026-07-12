# Canonical Academic 10 kW EESM Geometry Design

**Status:** Approved geometry baseline; awaiting written-spec review before implementation  
**Date:** 2026-07-12  
**Authoritative workspace:** `C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline`  
**Target project:** `aedt_mcp/tmp/aedt_projects/eesm_qual/eesm_qual.aedt`  
**Target solver:** AEDT Student 2025 R2, Maxwell 2-D Magnetostatic

## 1. Purpose and boundary

Build a reproducible academic electrically excited synchronous machine (EESM)
for qualifying the three-current magnetic-map workflow:

```text
(id_a, iq_a, if_a) -> (lambda_d_wb, lambda_q_wb, torque_fem_nm)
```

The machine is a methodology benchmark, not a reconstruction or validation of
a commercial motor. It is intentionally simple enough for AEDT Student while
retaining nonlinear saturation, stator-current cross-coupling, saliency, and a
controllable rotor field winding.

The first implementation is qualification-scale only. It may run the frozen
four-point smoke and eight-point pilot, but it must not start the Task 9 FEM
campaign until every Task 8 qualification check passes.

## 2. Rated operating point

| Parameter | Frozen value |
|---|---:|
| Continuous mechanical power | 10 kW |
| Base speed | 3,000 rpm |
| Maximum speed | 6,000 rpm |
| Base torque | 31.83 N.m |
| Pole count / pole pairs | 4 / 2 |
| DC-link voltage used by downstream study | 400 V |
| Peak phase-voltage limit | 230.94 V (`400/sqrt(3)`) |
| Peak dq stator-current domain | `id = -120..0 A`, `iq = 0..120 A` |
| DC field-current domain | `if = 0..15 A` |

The qualification pilot includes a small positive-`id` sign-check point outside
the training domain. It remains role `reference` and cannot enter training,
selection, or scheduler-audit data.

## 3. Frozen radial geometry

All dimensions are millimetres unless stated otherwise. Geometry is centered
at `(0, 0)` and uses an XY cross-section.

| Feature | Frozen value |
|---|---:|
| Stator outer diameter | 180.0 |
| Stator bore diameter | 110.0 |
| Air gap | 0.6 |
| Rotor outer diameter | 108.8 |
| Shaft diameter | 40.0 |
| Active stack length | 120.0 |
| Stator slots | 24 |
| Slot mechanical pitch | 15 degrees |
| Stator yoke minimum radial thickness | 15.0 |
| Rotor poles | 4 |
| Rotor mechanical pole pitch | 90 degrees |
| Pole-arc ratio | 0.65 |
| Pole-shoe angular span | 58.5 mechanical degrees |
| Rotor hub outer radius | 34.0 |
| Pole body radial span | radius 34.0 to 49.0 |
| Pole body tangential width | 20.0 |
| Pole-shoe radial span | radius 49.0 to 54.4 |
| Exterior solution-region radius | 135.0 |

### 3.1 Stator slot template

Use one parallel-sided open-slot template and duplicate it 24 times:

- slot centerlines are offset by 7.5 mechanical degrees from the +X axis;
- slot opening at the bore: 2.0 mm tangential width;
- tooth-tip / wedge radial depth: 1.5 mm;
- slot body tangential width: 7.0 mm;
- slot body radial depth below the tooth tip: 18.5 mm;
- total slot radial depth: 20.0 mm;
- slot bottom radius: 1.0 mm where supported; a straight bottom is acceptable
  only if the Student mesher cannot retain the radius below 2,000 triangles.

The resulting minimum stator back iron is 15 mm. No automatic optimization or
dimension sweep is permitted during qualification.

### 3.2 Rotor pole and field-coil template

Construct four identical salient poles at 0, 90, 180, and 270 mechanical
degrees. Each pole has the frozen body and shoe dimensions above. Place one
field-coil region around each pole body:

- coil window radial span: radius 36.0 to 47.0 mm;
- coil window tangential width per side of pole body: 7.0 mm;
- coil copper fill factor: 0.45;
- 80 series turns per pole;
- adjacent pole coils are connected so the air-gap poles alternate N/S;
- the Maxwell winding group is named `Field` and is driven by local variable
  `If` in amperes DC.

The shaft is nonmagnetic stainless steel. No damper cage, permanent magnets,
brushless exciter, skew, end turns, or axial leakage model is included.

## 4. Stator winding

Use a three-phase, double-layer distributed winding with 24 slots, 4 poles,
and `q = 2` slots per pole per phase. Coil pitch is six slots (90 mechanical
degrees, full pitch). Use 36 series turns per phase and copper fill factor
0.45.

Slot numbering begins at the first slot centerline, 7.5 mechanical degrees
from +X, and proceeds counter-clockwise. Phase belts repeat for slots 13-24:

| Slots | Phase belt |
|---|---|
| 1, 12, 13, 24 | A+ |
| 2, 3, 14, 15 | C- |
| 4, 5, 16, 17 | B+ |
| 6, 7, 18, 19 | A- |
| 8, 9, 20, 21 | C+ |
| 10, 11, 22, 23 | B- |

Create winding groups `PhaseA`, `PhaseB`, and `PhaseC`. Local variables `Id`
and `Iq` are peak dq amperes. At frozen electrical rotor angle
`theta_e = 0`, apply:

```text
Ia =  Id
Ib = -0.5*Id + 0.866025403784*Iq
Ic = -0.5*Id - 0.866025403784*Iq
```

The phase-current signs and winding directions must be verified by the pilot;
they are not accepted merely because the solve converges.

## 5. Materials and electromagnetic assumptions

- Stator and rotor laminations: nonlinear `M270-35A` from the AEDT material
  library, including its B-H curve.
- Stator and field coils: copper with stranded-winding treatment.
- Shaft: nonmagnetic stainless steel.
- Exterior region: vacuum/air.
- Model depth: 120 mm.
- Rotor position: fixed at `theta_e = 0` for the initial map convention.

If `M270-35A` is unavailable, stop and record the missing material. Do not
silently substitute another steel. Any approved substitute requires a new
`material_revision` and an updated specification.

## 6. Maxwell project contract

The saved AEDT objects use these exact names:

| Object | Required name |
|---|---|
| Project | `eesm_qual` |
| Maxwell design | `EESM_2D_Qual` |
| Solution type | `Magnetostatic`, XY |
| Setup | `Setup_Qual` |
| Solution | `Setup_Qual : LastAdaptive` |
| Torque parameter | `TorqueRotor` |
| Stator windings | `PhaseA`, `PhaseB`, `PhaseC` |
| Rotor field winding | `Field` |
| Local variables | `Id`, `Iq`, `If`, `Ia`, `Ib`, `Ic`, `theta_e` |

Use vector-potential zero on the outer boundary of the 135 mm-radius solution
region. The rotor core, field coils, and shaft comprise the rotating object
set for torque calculation, but no transient motion band is required.

## 7. Solver and mesh gate

AEDT Student limits Maxwell 2-D models to 2,000 triangles. The qualification
model therefore uses:

- TAU 2-D mesher;
- maximum eight adaptive passes;
- 1% target energy error;
- local length refinement in the air gap and pole-shoe tips;
- final triangle count between 800 and 1,950;
- at least two effective elements across the 0.6 mm air gap;
- local solve only.

If the mesh exceeds 1,950 triangles, simplify slot-bottom fillets first. Do
not change air gap, pole arc, slot count, current domains, or material to meet
the limit. Record the final triangle count and adaptive-pass count in every
qualification row.

## 8. Outputs and Park convention

Export raw `FluxLinkage(PhaseA)`, `FluxLinkage(PhaseB)`, and
`FluxLinkage(PhaseC)` in Wb plus Maxwell electromagnetic torque in N.m.
Preserve raw phase results. Convert phase flux to dq using the existing
Task 8 transform at `theta_e = 0`. Direct `Flux_d` or `Flux_q` report export
is not authoritative.

The exporter must populate:

```text
project,design,setup,rotor_position_deg,mesh_elements,adaptive_passes,
solver_status,solver_message,lambda_d_wb,lambda_q_wb,torque_fem_nm,pole_pairs
```

## 9. Qualification sequence and stop rules

1. Create and validate geometry, materials, windings, variables, torque
   parameter, boundary, setup, and mesh without running a current sweep.
2. Run only the four-point smoke at `If = 2 A`:
   `field_only`, `q_current`, `negative_d`, `combined_rated`.
3. Inspect status JSON, progress CSV, raw ABC exports, convergence, mesh count,
   and solver messages. Keep `SMOKE_APPROVED = False` until reviewed.
4. After explicit smoke approval, run the remaining four pilot points.
5. Normalize results and generate `qualification_report.json`.

Stop before Task 9 if any of these holds:

- project/design/setup/object names differ from the contract;
- phase or field excitation is missing or has unexplained sign behavior;
- a pilot solve fails or does not converge;
- mesh evidence is missing or exceeds the Student limit;
- ABC flux is missing, nonfinite, or inconsistent with the declared Park map;
- field current does not produce the expected d-axis flux response;
- reported torque and flux-recomputed torque have an unexplained discrepancy;
- any qualification check is `fail` or `inconclusive`.

## 10. Testing and evidence budget

Do not add geometry unit tests or one test per Maxwell object. Reuse the
existing four-case `test_maxwell_adapter.py` contract. Verification evidence
for this design is the saved AEDT project, GUI status JSON, raw exports,
canonical pilot CSV, qualification report, mesh/pass counts, and reviewed
screenshots/logs.

## 11. Provenance and references

The geometry is an original academic benchmark informed by published WFSM
scales rather than copied from one commercial machine. Reference examples
include:

- Ansys Maxwell Student limitations: 2-D mesh limit and local-solve boundary:
  <https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v242/en/Subsystems/Maxwell/Content/GettingStarted/MaxwellStudentLimitations.htm>
- A published 4-pole/24-slot WFSM scale with 130/80 mm diameters, 0.5 mm air
  gap, and 90 mm stack:
  <https://www.mdpi.com/1996-1073/14/15/4427>
- A traction-oriented wound-field machine scale with 168/108 mm diameters,
  0.4 mm air gap, 105 mm stack, and M270-35A steel:
  <https://www.mdpi.com/2032-6653/16/1/25>

The frozen dimensions in this specification intentionally enlarge those
research-scale precedents to the approved 10 kW / 31.83 N.m methodology
benchmark while retaining a Student-compatible 2-D topology.
