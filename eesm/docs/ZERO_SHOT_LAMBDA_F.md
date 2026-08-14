# Zero-shot λf, seed-averaged

Gauge is fit on **train rows only**. Selection never enters the gauge.
Seeds are the same eight model seeds as the supervised energy-net study.

At budget 256 the median gauge-fixed λf RMSE is 1.5–4.0% of the
selection-set standard deviation (0.696 Wb) and beats the If-only cubic
control by 21–59×. Gauge R² is 0.97–1.00, i.e. the residual is a function
of If as the identifiability argument requires.

At budget 64 the ablation is not asymptotic (R² 0.60–0.82, control
ratio 2.7–5.3×). Report that. Do not hide it.

Seed-median stator torque is **not** uniformly improved by field
supervision. Quote λf recovery as the claim, not a universal stator win.

Artifact: `out/eesm/zero_shot_seed_study_20260813/zero_shot_seed_study.json`.
