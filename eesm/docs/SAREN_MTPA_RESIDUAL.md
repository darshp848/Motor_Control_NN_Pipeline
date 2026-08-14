# Sárén MTPA residual as an \(L_\mathrm{diff}\) consumer

**Not** a QCQP reference generator and **not** EESM-004/005.
Metric: arXiv:2607.08528 eqs. (6)–(8), stator 2-DOF at the eight FD
anchors, comparing each family's \((\psi,L)\) to the FEM Jacobian.

The one-Newton-step current correction is reported but is **not** a
controller reference error here: the anchors are not MTPA points, so the
step is \(O(100\,\mathrm{A})\). Use \(\Delta e = |e_\mathrm{hat}-e_\mathrm{FEM}|\)
as the priced residual.
