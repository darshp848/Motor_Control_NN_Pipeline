# PWA construction fidelity (Steyaert 2023 / Parson-Scherban 2026)

**Status:** checked against the papers, not against vendor source.
**Does not:** claim that family `pwa` *is* Preindl's PWA.

## What the papers do

Parson-Scherban, Steyaert, Anderson & Preindl, arXiv:2604.17165 §2.3
(citing Steyaert *et al.*, IEEE TIE 2023):

1. Sample the current box \(\mathcal{I}\subset\mathbb{R}^3\) with FEA points.
2. Partition by **Delaunay triangulation of those sample points**.
3. On simplex \(\mathcal{I}_j\), fit \(\lambda = L_j i + \psi_j\) by
   **least squares to the FEA data within \(\mathcal{I}_j\)**.
4. Represent each simplex as half-spaces \(\{i: A_j i \le b_j\}\) for the
   QCQP consumer.

Steyaert 2023 is a WRSM PWA magnetic/state-space model over
\((i_r,i_d,i_q)\). The 2026 paper uses a **uniform FEA grid** then Delaunay
(§4.1). Their local \(L\) is assumed symmetric with \(L_{rq}=0\).

## What `pwa` in this repo does

| Item | Papers | This repo (default) |
|---|---|---|
| Partition | Delaunay of FEA samples in **amperes** | Delaunay of **normalized** \((i_d,i_q,i_f)\) |
| Affine fit | LS to FEA data *within* the simplex | LS on the **four vertices** (exact interpolant in 3-D) |
| Sample design | Uniform FEA grid in the cited 2026 run | tensor / random / LHS at 64/128/256 |
| Outside the hull | not used (stay in sampled \(\mathcal{I}\)) | nearest training vertex |
| \(L_{rq}=0\), \(L=L^\top\) | assumed for the QCQP | **not** enforced |
| Half-space \(A_j,b_j\) | stored for the QCQP | not stored (`find_simplex` only) |
| Outputs | \((\lambda_r,\lambda_d,\lambda_q)\) | \((\lambda_d,\lambda_q,\lambda_{f,\mathrm{terminal}})\) |

Delaunay is **not** invariant under independent axis scaling. Fitting in the
normalized box is therefore not the same triangulation as Delaunay in
amperes. Set `delaunay_space: physical` to match the papers' current space.

On a non-degenerate tetrahedron, vertex LS *is* the unique interpolating
affine map. Extra interior FEA points inside a simplex appear only if the
triangulation is coarser than the FEA cloud. Our designs *are* the cloud,
so vertex LS matches "LS within \(\mathcal{I}_j\)" for those designs.

## Claim language

Allowed: "an as-described Delaunay PWA reimplementation."

Not allowed in the abstract: "PWA is worse" or "Steyaert/Preindl PWA
underperforms," unless `delaunay_space='physical'` is used and the
remaining mismatches (no \(L_{rq}=0\), no QCQP half-spaces, our sample
designs) are stated.

The physics-gate result that PWA passes only on the **tensor grid** is
consistent with the papers' uniform-grid Delaunay: random/LHS clouds
produce sliver tetrahedra and noisy Jacobians.

A same-day rescore (`out/eesm/pwa_saren_study_20260813/`) with
`delaunay_space='physical'` did **not** change any pass/fail: tensor
64/128/256 still pass, all random/LHS cells still fail. Torque RMSE on
the irregular designs got worse in physical space. Matching the papers'
current units does not fix a sliver cloud.

The roadmap line that this is "exactly the Steyaert/Preindl construction"
is withdrawn. Use this note instead.
