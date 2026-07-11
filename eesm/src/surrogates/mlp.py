"""Compact deterministic PyTorch MLP baseline for EESM flux prediction."""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from surrogates.base import FluxSurrogate


class CompactMLPSurrogate(FluxSurrogate):
    family = "compact_mlp"

    def _fit_normalized(self, X: np.ndarray, y: np.ndarray) -> None:
        torch.manual_seed(self.seed)
        hidden = int(self.config.get("hidden_width", 32))
        learning_rate = float(self.config.get("learning_rate", 0.01))
        epochs = int(self.config.get("epochs", 300))
        self.hyperparameters_ = {
            "architecture": [3, hidden, hidden, 2],
            "activation": "tanh",
            "dtype": "float64",
            "loss": "mean_squared_error",
            "adam": {
                "lr": learning_rate, "betas": [0.9, 0.999], "eps": 1e-8,
                "weight_decay": 0, "amsgrad": False, "maximize": False,
                "foreach": None, "capturable": False, "differentiable": False,
                "fused": None, "decoupled_weight_decay": False,
            },
            "epochs": epochs,
        }
        self.model_ = nn.Sequential(
            nn.Linear(3, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, 2),
        ).to(dtype=torch.float64)
        inputs = torch.as_tensor(X, dtype=torch.float64)
        targets = torch.as_tensor(y, dtype=torch.float64)
        optimizer = torch.optim.Adam(
            self.model_.parameters(),
            lr=learning_rate,
            betas=(0.9, 0.999), eps=1e-8, weight_decay=0,
            amsgrad=False, maximize=False, foreach=None, capturable=False,
            differentiable=False, fused=None,
            decoupled_weight_decay=False,
        )
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
