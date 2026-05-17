"""PriceTorchMLP — PyTorch nn.Module for on-the-fly directional prediction on GPU/CPU."""

from __future__ import annotations

import logging
from typing import Any, Dict

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


class PriceTorchMLP(nn.Module):
    """3-layer MLP trained on-the-fly from price bars.

    Architecture: Linear(3,64) → BN → ReLU → Dropout(0.3)
               → Linear(64,32) → BN → ReLU → Dropout(0.3)
               → Linear(32,1) → Sigmoid (applied at inference)

    Trains on the last ~600 bars of return, volatility range, and
    3-period momentum features.
    """

    def __init__(self, device: str | None = None):
        super().__init__()
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        self.fc1 = nn.Linear(3, 64)
        self.bn1 = nn.BatchNorm1d(64)
        self.drop1 = nn.Dropout(0.3)
        self.fc2 = nn.Linear(64, 32)
        self.bn2 = nn.BatchNorm1d(32)
        self.drop2 = nn.Dropout(0.3)
        self.fc3 = nn.Linear(32, 1)
        self.to(self._device)

    @property
    def device(self) -> str:
        return self._device

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.bn1(self.fc1(x)))
        x = self.drop1(x)
        x = F.relu(self.bn2(self.fc2(x)))
        x = self.drop2(x)
        return self.fc3(x)

    def evaluate(self, ticker: str, candles_data: list) -> Dict[str, Any]:
        """Train on-the-fly and predict directional probability.

        Same contract as PriceMLP.evaluate().
        """
        try:
            if not candles_data or len(candles_data) < 50:
                return {
                    "mlp_score": 0.5,
                    "verdict": "WAIT",
                    "confidence": 0.0,
                    "error": "Insufficient data for training (min: 50).",
                    "source": "torch_mlp",
                }

            X, y = self._build_features(candles_data)

            if len(X) < 30:
                return {
                    "mlp_score": 0.5,
                    "verdict": "WAIT",
                    "confidence": 0.0,
                    "error": "Insufficient valid features after parsing.",
                    "source": "torch_mlp",
                }

            if len(np.unique(y)) < 2:
                return {
                    "mlp_score": 0.5,
                    "verdict": "WAIT",
                    "confidence": 0.0,
                    "error": "Only one class in target. Cannot converge.",
                    "source": "torch_mlp",
                }

            convergence = self._train(X, y)

            prob_up = self._predict_last(candles_data)

            if prob_up > 0.65:
                verdict = "BUY"
            elif prob_up < 0.35:
                verdict = "SELL"
            else:
                verdict = "WAIT"

            confidence = abs(prob_up - 0.5) * 2

            return {
                "mlp_score": float(prob_up),
                "verdict": verdict,
                "confidence": float(confidence),
                "loss_convergence": "stable" if convergence else "unstable",
                "source": "torch_mlp",
            }

        except Exception as e:
            logger.error("PriceTorchMLP failed for %s: %s", ticker, e)
            return {
                "mlp_score": 0.5,
                "verdict": "WAIT",
                "confidence": 0.0,
                "error": str(e),
                "source": "torch_mlp",
            }

    def _build_features(self, candles_data: list) -> tuple[np.ndarray, np.ndarray]:
        X, y_list = [], []
        for i in range(3, len(candles_data) - 1):
            try:
                c = candles_data[i]
                c_prev1 = candles_data[i - 1]
                c_prev3 = candles_data[i - 3]

                close = float(c["close"])
                high = float(c["high"])
                low = float(c["low"])
                prev_close = float(c_prev1["close"])
                prev3_close = float(c_prev3["close"])

                if close == 0 or prev_close == 0 or prev3_close == 0:
                    continue

                ret = (close - prev_close) / prev_close
                vol = (high - low) / close
                mom = (close - prev3_close) / prev3_close

                next_close = float(candles_data[i + 1]["close"])
                target = 1 if next_close > close else 0

                X.append([ret, vol, mom])
                y_list.append(target)
            except Exception:
                continue
        return np.array(X, dtype=np.float32), np.array(y_list, dtype=np.float32)

    def _train(self, X: np.ndarray, y: np.ndarray) -> bool:
        """Train on CPU/GPU tensor data. Returns True if converged before max epochs."""
        mean = X.mean(axis=0)
        std = X.std(axis=0) + 1e-8
        X_norm = (X - mean) / std
        self._norm_mean = mean
        self._norm_std = std

        n_val = max(int(len(X_norm) * 0.15), 1)
        X_val = torch.tensor(X_norm[-n_val:], device=self._device)
        y_val = torch.tensor(y[-n_val:], device=self._device).unsqueeze(1)
        X_tr = torch.tensor(X_norm[:-n_val], device=self._device)
        y_tr = torch.tensor(y[:-n_val], device=self._device).unsqueeze(1)

        optimizer = torch.optim.Adam(self.parameters(), lr=1e-3, weight_decay=1e-4)
        loss_fn = nn.BCEWithLogitsLoss()

        best_val_loss = float("inf")
        patience_counter = 0
        converged = False

        for epoch in range(200):
            self.train()
            optimizer.zero_grad()
            logits = self(X_tr)
            loss = loss_fn(logits, y_tr)
            loss.backward()
            optimizer.step()

            self.eval()
            with torch.no_grad():
                val_loss = loss_fn(self(X_val), y_val).item()

            if val_loss < best_val_loss - 1e-6:
                best_val_loss = val_loss
                patience_counter = 0
            else:
                patience_counter += 1

            if patience_counter >= 20:
                converged = True
                break

        if epoch >= 199 and not converged:
            converged = False

        self.eval()
        return converged

    def _predict_last(self, candles_data: list) -> float:
        last_c = candles_data[-1]
        last_c_prev1 = candles_data[-2]
        last_c_prev3 = candles_data[-4]

        close = float(last_c["close"])
        high = float(last_c["high"])
        low = float(last_c["low"])
        prev_close = float(last_c_prev1["close"])
        prev3_close = float(last_c_prev3["close"])

        last_ret = (close - prev_close) / prev_close if prev_close else 0
        last_vol = (high - low) / close if close else 0
        last_mom = (close - prev3_close) / prev3_close if prev3_close else 0

        raw = np.array([[last_ret, last_vol, last_mom]], dtype=np.float32)
        norm = (raw - self._norm_mean) / self._norm_std
        tensor = torch.tensor(norm, device=self._device)

        with torch.no_grad():
            logit = self(tensor)
            prob = torch.sigmoid(logit).item()
        return float(prob)
