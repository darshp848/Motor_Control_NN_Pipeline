"""Co-energy network: λd, λq = (2/3) ∇_{id,iq} W′(id, iq, If)."""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from surrogates.base import FluxSurrogate


class EnergyGradientSurrogate(FluxSurrogate):
    """Amplitude-invariant energy net. Mixed partials of W′ are symmetric."""

    family = "energy_gradient_net"

    def _flux_physical(self, X_n: torch.Tensor, create_graph: bool) -> torch.Tensor:
        """Map normalized currents to physical (λd, λq)."""
        X_n = X_n.requires_grad_(True)
        energy = self.model_(X_n).squeeze(-1)
        grads = torch.autograd.grad(
            energy.sum(), X_n, create_graph=create_graph, retain_graph=create_graph
        )[0]
        scale = torch.as_tensor(self.x_scale_, dtype=torch.float64, device=X_n.device)
        dW_di = grads / scale
        return (2.0 / 3.0) * dW_di[:, :2]

    def _fit_normalized(self, X: np.ndarray, y: np.ndarray) -> None:
        torch.manual_seed(self.seed)
        hidden = int(self.config.get("hidden_width", 32))
        learning_rate = float(self.config.get("learning_rate", 0.01))
        epochs = int(self.config.get("epochs", 400))
        self.hyperparameters_ = {
            "architecture": [3, hidden, hidden, 1],
            "activation": "tanh",
            "output": "coenergy_W_prime",
            "flux_rule": "lambda_dq = (2/3) dW/d(id,iq)",
            "dtype": "float64",
            "loss": "mse_physical_flux",
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
        optimizer = torch.optim.Adam(
            self.model_.parameters(),
            lr=learning_rate,
            betas=(0.9, 0.999),
            eps=1e-8,
        )
        self.model_.train()
        for _ in range(epochs):
            optimizer.zero_grad()
            predicted = self._flux_physical(inputs, create_graph=True)
            loss = nn.functional.mse_loss(predicted, y_phys)
            loss.backward()
            optimizer.step()
        self.model_.eval()

    def _predict_normalized(self, X: np.ndarray) -> np.ndarray:
        inputs = torch.as_tensor(X, dtype=torch.float64)
        flux = self._flux_physical(inputs, create_graph=False).detach().cpu().numpy()
        return (flux - self.y_mean_) / self.y_scale_
