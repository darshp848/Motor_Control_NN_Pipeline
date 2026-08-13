"""Co-energy network for the EESM magnetic map.

The network learns a scalar co-energy W'(id, iq, If). Flux linkages are its
scaled gradient, in the amplitude-invariant convention of
`eesm/docs/DQ_CONVENTIONS.md`:

    lambda_d = (2/3) dW'/d id
    lambda_q = (2/3) dW'/d iq
    lambda_f =       dW'/d If      (TERMINAL field flux linkage)

Because every output is a partial derivative of one scalar potential, all three
reciprocity identities hold to machine precision by construction rather than by
penalty. That is the property being tested in Phase 1.

Two supervision modes, both pre-registered:

`field_supervision = true`  (default for the Phase 1 v2 study)
    Train on (lambda_d, lambda_q, lambda_f_terminal). Three outputs.

`field_supervision = false` (the zero-shot ablation)
    Train on (lambda_d, lambda_q) only, then read lambda_f off the same
    potential. Matching only the stator gradient leaves W' free up to an
    additive g(If), so lambda_f is recoverable only up to g'(If) -- a ONE
    dimensional gauge. `eesm/src/metrics/field_gauge.py` fits that gauge on
    training rows and nothing else.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from surrogates.base import FluxSurrogate

#: Output channel order produced by the potential's gradient.
CHANNELS = ("lambda_d_wb", "lambda_q_wb", "lambda_f_terminal_wb")


class EnergyGradientSurrogate(FluxSurrogate):
    """Amplitude-invariant co-energy net. Mixed partials of W' are symmetric."""

    family = "energy_gradient_net"

    def __init__(self, seed, config=None):
        super().__init__(seed=seed, config=config)
        self.field_supervision = bool(
            self.config.get("field_supervision", True)
        )
        # Supervised channel count. The potential always yields three.
        self.n_outputs = 3 if self.field_supervision else 2

    # ------------------------------------------------------------------
    # potential and its gradient
    # ------------------------------------------------------------------
    def _all_channels(
        self, X_n: torch.Tensor, create_graph: bool
    ) -> torch.Tensor:
        """All three physical flux channels from the gradient of W'."""
        X_n = X_n.requires_grad_(True)
        energy = self.model_(X_n).squeeze(-1)
        grads = torch.autograd.grad(
            energy.sum(), X_n, create_graph=create_graph, retain_graph=create_graph
        )[0]
        scale = torch.as_tensor(self.x_scale_, dtype=torch.float64, device=X_n.device)
        # chain rule back to physical currents; the net sees normalized inputs
        dW_di = grads / scale
        return torch.stack(
            [
                (2.0 / 3.0) * dW_di[:, 0],
                (2.0 / 3.0) * dW_di[:, 1],
                dW_di[:, 2],
            ],
            dim=1,
        )

    # ------------------------------------------------------------------
    # fit / predict
    # ------------------------------------------------------------------
    def _fit_normalized(self, X: np.ndarray, y: np.ndarray) -> None:
        torch.manual_seed(self.seed)
        hidden = int(self.config.get("hidden_width", 64))
        learning_rate = float(self.config.get("learning_rate", 0.01))
        epochs = int(self.config.get("epochs", 3000))
        n_sup = y.shape[1]
        self.hyperparameters_ = {
            "architecture": [3, hidden, hidden, 1],
            "activation": "tanh",
            "output": "coenergy_W_prime",
            "flux_rule": "lambda_dq = (2/3) dW/d(id,iq); lambda_f = dW/dIf",
            "field_supervision": self.field_supervision,
            "supervised_channels": list(CHANNELS[:n_sup]),
            "dtype": "float64",
            # per-channel normalized loss: lambda_f_terminal is about an order
            # of magnitude larger than lambda_d, so an unweighted physical MSE
            # would let the field channel swamp the stator channels
            "loss": "mse_per_channel_normalized_flux",
            "epochs": epochs,
            "learning_rate": learning_rate,
        }
        self.model_ = nn.Sequential(
            nn.Linear(3, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, 1),
        ).to(dtype=torch.float64)

        inputs = torch.as_tensor(X, dtype=torch.float64)
        y_phys = torch.as_tensor(
            y * self.y_scale_ + self.y_mean_, dtype=torch.float64
        )
        y_scale = torch.as_tensor(self.y_scale_, dtype=torch.float64)
        optimizer = torch.optim.Adam(
            self.model_.parameters(), lr=learning_rate, betas=(0.9, 0.999), eps=1e-8
        )
        self.model_.train()
        for _ in range(epochs):
            optimizer.zero_grad()
            predicted = self._all_channels(inputs, create_graph=True)[:, :n_sup]
            residual = (predicted - y_phys) / y_scale
            loss = (residual ** 2).mean()
            loss.backward()
            optimizer.step()
        self.model_.eval()

    def _predict_normalized(self, X: np.ndarray) -> np.ndarray:
        inputs = torch.as_tensor(X, dtype=torch.float64)
        flux = self._all_channels(inputs, create_graph=False).detach().cpu().numpy()
        return (flux[:, : self.n_outputs] - self.y_mean_) / self.y_scale_

    # ------------------------------------------------------------------
    # zero-shot field channel
    # ------------------------------------------------------------------
    def predict_field(self, X: np.ndarray) -> np.ndarray:
        """Terminal lambda_f in Wb, read straight off dW'/dIf.

        Defined whether or not lambda_f was supervised. Under
        `field_supervision = false` the returned values carry an unknown
        additive g'(If); fix it with `metrics.field_gauge` before scoring.
        """
        if not self._fitted:
            raise RuntimeError("surrogate must be fitted before prediction")
        X_array = np.asarray(X, dtype=np.float64)
        if X_array.ndim != 2 or X_array.shape[1] != 3:
            raise ValueError("X must have shape (n, 3)")
        normalized = (X_array - self.x_mean_) / self.x_scale_
        inputs = torch.as_tensor(normalized, dtype=torch.float64)
        flux = self._all_channels(inputs, create_graph=False).detach().cpu().numpy()
        return flux[:, 2]
