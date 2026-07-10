# Units and conventions (IPM Stage 0 freeze)

Machine-readable twin: `configs/ipm_experiment_manifest.json` and `data/motor_params_clean.json`.

## Currents

| Symbol | Meaning | Units |
|--------|---------|-------|
| \(i_d, i_q\) | dq-frame **peak** phase current amplitudes | A (peak) |
| \(I_{s}\) | \(\sqrt{i_d^2 + i_q^2}\) | A (peak) |
| `rated_current_rms_a` | RMxprt RMS armature current | A (rms) |
| `i_rated_peak_a` | \(\sqrt{2}\times\) RMS | A (peak) |
| `i_max_peak_a` | Stator current limit used in MTPA/FW | A (peak), default 6.0 |

Training FEM map uses a **wide** current box (Id ∈ [-300, 0] A, Iq ∈ [0, 300] A) as a saturation stress test. The controller search domain is the half-disk \(|I_s| \le 6\) A with \(i_d \le 0\).

## Flux

| Item | Value |
|------|--------|
| CSV columns `Phi_d`, `Phi_q` | **Raw FEM** flux linkages (unscaled) |
| `flux_scale` | Multiplier to SI-consistent Wb·turns for torque |
| Where scale applies | Only in MTPA `FluxSurrogate` (and audit), **not** re-applied in training |

Definition:

\[
T_\text{implied} = \tfrac{3}{2} P\,(\Phi_d I_q - \Phi_q I_d)
\quad\text{at }(I_d,I_q)=(0, I_{\text{rated,peak}})
\]

\[
\text{flux\_scale} = T_{\text{rated}} / T_{\text{implied}}
\]

with \(P =\) **pole pairs**. Frozen value ≈ **11.861** for the Student-mesh IPM project.

## Poles

- `poles` = 4 (pole count)
- `pole_pairs` = 2 (**use this in \(T\) and \(\omega_e\)**)

## Park / dq

- \(\theta_{re} = 0\): d-axis aligned with Phase A (matches FEM export scripts)
- Inverse Park currents and Park fluxes use the same transforms as `pipeline/physics.py`

## Torque and voltage

\[
T = \tfrac{3}{2} P\,(\lambda_d i_q - \lambda_q i_d)
\]

\[
v_d = R_s i_d - \omega_e \lambda_q,\quad
v_q = R_s i_q + \omega_e \lambda_d
\]

\[
\omega_e = \omega_{\text{mech}} \cdot P,\quad
\omega_{\text{mech}} = 2\pi\cdot n_{\text{rpm}}/60
\]

SVPWM limit: \(V_{\max} = V_{dc}/\sqrt{3}\) (phase peak).

## Resistance / bus

| Key | Frozen value | Notes |
|-----|--------------|-------|
| `rs_ohm` | 2.15938 | Fallback from RMxprt; variable probe may fail in Student |
| `vdc_v` | 311 | Default \(\sqrt{2}\cdot 220\) EV-style bus |
| `t_rated_nm` | 2.89531 | RMxprt rated torque |

## Domain labels (validation)

| Label | Meaning |
|-------|---------|
| `in_domain_interpolation` | Inside training Id/Iq rectangle |
| `boundary` | Near domain edge (≈ one grid step) |
| `extrapolation` | Outside training rectangle (e.g. Id > 0) |

Report errors **separately**. Do not mix into a single “generalization” score.
