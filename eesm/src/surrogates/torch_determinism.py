"""CPU-only Torch determinism for EESM surrogate fits.

Phase 0/1 only called ``torch.manual_seed``. That is not enough for the
energy-gradient net: Adam + autograd through W' can change across thread
counts and library builds. Paper 2 requires a pinned, single-thread,
deterministic-algorithm fit.
"""

from __future__ import annotations

import os
from typing import Any

import torch


DEFAULT_NUM_THREADS = 1


def configure_torch_determinism(
    seed: int,
    num_threads: int = DEFAULT_NUM_THREADS,
) -> dict[str, Any]:
    """Pin seeds, thread count, and deterministic algorithms. CPU only."""
    threads = int(num_threads)
    if threads < 1:
        raise ValueError("num_threads must be >= 1")
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["MKL_NUM_THREADS"] = str(threads)
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

    torch.set_num_threads(threads)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        # Torch allows this only before the runtime starts parallel work.
        pass

    torch.use_deterministic_algorithms(True, warn_only=False)
    return {
        "seed": int(seed),
        "device": "cpu",
        "torch_version": torch.__version__,
        "torch_deterministic_algorithms": True,
        "num_threads": threads,
        "interop_threads": 1,
        "cuda_used": False,
    }


def adam_deterministic_kwargs(learning_rate: float) -> dict[str, Any]:
    """Adam settings that avoid foreach/fused kernels."""
    return {
        "lr": float(learning_rate),
        "betas": (0.9, 0.999),
        "eps": 1e-8,
        "weight_decay": 0,
        "amsgrad": False,
        "foreach": False,
        "capturable": False,
        "differentiable": False,
        "fused": False,
    }
