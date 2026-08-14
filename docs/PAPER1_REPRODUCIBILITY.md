# Reproducing the equal-budget EESM paper artifact

This guide is for the study reported in *When Validation Gates Fail to
Discriminate: A Predeclared Equal-Budget EESM Flux-Map Study*. It separates
three distinct tasks: verifying the archived evidence, rerunning the offline
surrogate study, and regenerating FEM truth. Do not treat a mock FEMM run as
physics evidence.

## 1. Exact revision and environment

Use the immutable commit cited by the manuscript. Confirm it before doing
anything else:

```pwsh
git rev-parse HEAD
```

The reported run used Python 3.11.9, NumPy 2.4.6, SciPy 1.17.1,
scikit-learn 1.9.0, pandas 3.0.3, Matplotlib 3.11.0, and PyTorch
2.11.0+cu128. Model training stayed on the default CPU device; the `+cu128`
build tag is not a CUDA-computation claim. Create the known-good offline
environment with:

```pwsh
py -3.11 -m venv .venv-paper1
.\.venv-paper1\Scripts\python -m pip install -U pip
.\.venv-paper1\Scripts\python -m pip install -r requirements-paper1.txt
.\.venv-paper1\Scripts\python -m pytest eesm/tests -q
```

The broader `requirements.txt` remains a development range. The paper-specific
file is pinned because floating minimum versions are not an archival
environment specification.

## 2. Verify the archived evidence without FEMM

The repository carries the compact inputs and summaries needed to verify every
SHA-256 entry in `out/eesm/phase0_close_20260813/result_bundle.json`:

- the 1759-row FEMM campaign CSV;
- the original 36-run summary;
- the phase-close result;
- the frozen threshold proposal and 1760-identity point freeze.

Run:

```pwsh
.\.venv-paper1\Scripts\python -m eesm.verify_result_bundle
```

The command exits nonzero if an artifact is absent, modified, or resolves
outside the repository. The published summary can then be inspected at
`out/eesm/phase0_close_20260813/phase0_close.json`; its `ranking_runs` array is
the source for the paper's 36-cell table.

The archived CSV and summary make the reported hashes independently
checkable. They do not make a second FEM solve bit-for-bit identical: FEMM,
Triangle meshing, Windows, and floating-point-library details can change file
bytes even when engineering metrics agree.

## 3. Install and check the live solver

Fresh FEM truth generation is Windows-only. Install FEMM 4.2 build 21Apr2019
from the FEMM project and pyFEMM 0.1.3 into the paper environment:

```pwsh
.\.venv-paper1\Scripts\python -m pip install pyfemm==0.1.3
.\.venv-paper1\Scripts\python -m eesm.run_femm_campaign --check
```

The check must report `femm_importable: true` and an empty `missing_api` list.
Invoke the runner with `python -m`; running `python eesm/run_femm_campaign.py`
can make the repository's `eesm/femm` package shadow pyFEMM. See
[`eesm/docs/FEMM_MIGRATION.md`](../eesm/docs/FEMM_MIGRATION.md) for the
version-matched API checks, one-point diagnostic, failure preservation, and
FEMM installation notes.

## 4. Recreate the machine and frozen point identities

The live runner builds the 90-degree EESM sector directly from
`eesm/femm/config.py`, `geometry.py`, and `section.py`; no prebuilt `.fem` file
is required. Generate a new copy of the point freeze without overwriting the
archived evidence:

```pwsh
.\.venv-paper1\Scripts\python -m eesm.femm.budget_points `
  --out out/eesm/reproduction_points
```

Expected counts are 1760 identities and 1759 FEMM-solvable rows. The analytic
origin is a training identity but is not sent to FEMM. Compare the new
`frozen_points.csv` hash with the archived
`out/eesm/femm_equal_budget_points_20260813/point_freeze.json` before solving.

For the smallest safe live diagnostic, solve one point into a disposable new
campaign root:

```pwsh
.\.venv-paper1\Scripts\python -m eesm.run_femm_campaign `
  --out out/eesm/reproduction_probe `
  --points out/eesm/reproduction_points/frozen_points.csv `
  --max-new-points 1
```

Confirm schema validity, 73,904 mesh elements, finite fluxes, and the expected
torque-convention fields before launching the full campaign.

## 5. Regenerate FEM truth and the 36-cell study

Use new output directories so the write-once evidence guards cannot mix a
reproduction with the archived campaign:

```pwsh
.\.venv-paper1\Scripts\python -m eesm.run_femm_campaign `
  --out out/eesm/reproduction_campaign `
  --points out/eesm/reproduction_points/frozen_points.csv

.\.venv-paper1\Scripts\python -m eesm.run_equal_budget_study `
  --config eesm/configs/eesm_experiment_manifest.json `
  --truth-csv out/eesm/reproduction_campaign/femm_results.csv `
  --out out/eesm/reproduction_study

.\.venv-paper1\Scripts\python -m eesm.run_phase0_close `
  --campaign out/eesm/reproduction_campaign/femm_results.csv `
  --study out/eesm/reproduction_study `
  --out out/eesm/reproduction_close
```

Success means 1759/1759 schema-valid FEM rows, 36/36 completed fits, the same
seven evaluable threshold outcomes, the same untestable selection-set boundary
criterion, and the same promoted candidate under the frozen ranking policy.
Compare engineering metrics, point identities, and gate decisions; do not use
wall-clock runtimes or regenerated file timestamps as equality criteria.

## 6. Scope of the artifact

The archived study supports the current-space map comparison and the post-hoc
reciprocity diagnostic. It does not contain replicated random/LHS designs,
independent full-machine torque truth across the map, or a frozen
speed--torque scheduler-command audit. Those are explicitly future studies,
not hidden reproduction steps.
