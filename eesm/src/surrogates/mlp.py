"""Compact deterministic PyTorch MLP baseline for EESM flux prediction."""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from surrogates.base import FluxSurrogate
from surrogates.torch_determinism import (
    adam_deterministic_kwargs,
    configure_torch_determinism,
)


class CompactMLPSurrogate(FluxSurrogate):
    family = "compact_mlp"

    def _fit_normalized(self, X: np.ndarray, y: np.ndarray) -> None:
        threads = int(self.config.get("num_threads", 1))
        determinism = configure_torch_determinism(self.seed, num_threads=threads)
        hidden = int(self.config.get("hidden_width", 32))
        learning_rate = float(self.config.get("learning_rate", 0.01))
        epochs = int(self.config.get("epochs", 300))
        n_out = int(y.shape[1])
        adam_kwargs = adam_deterministic_kwargs(learning_rate)
        self.hyperparameters_ = {
            "architecture": [3, hidden, hidden, n_out],
            "activation": "tanh",
            "dtype": "float64",
            "loss": "mean_squared_error",
            "adam": adam_kwargs,
            "epochs": epochs,
            "device": "cpu",
            "determinism": determinism,
        }
        self.model_ = nn.Sequential(
            nn.Linear(3, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, n_out),
        ).to(dtype=torch.float64)
        inputs = torch.as_tensor(X, dtype=torch.float64)
        targets = torch.as_tensor(y, dtype=torch.float64)
        optimizer = torch.optim.Adam(self.model_.parameters(), **adam_kwargs)
        for _ in range(epochs):
            optimizer.zero_grad()
            loss = nn.functional.mse_loss(self.model_(inputs), targets)
            loss.backward()
            optimizer.step()
        self.model_.eval()

    def _predict_normalized(self, X: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            prediction = self.model_(torch.as_tensor(X, dtype=torch.float64))
        return prediction.cpu().numpy()
