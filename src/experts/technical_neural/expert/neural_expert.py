import logging
import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PriceMLP:
    """
    On-the-fly MLP classifier trained on price-derived features.

    Uses the last 600 bars to fit an sklearn MLPClassifier on
    return, volatility range, and 3-period momentum — then predicts
    directional probability for the next bar.
    """

    def __init__(self):
        self.scaler = StandardScaler()
        # MLP idêntico a arquitetura proposta: Dense -> Dropout -> Dense -> ReLU
        # Usamos early_stopping=True (como Validation Holdout do NeuraLib)
        self.model = MLPClassifier(
            hidden_layer_sizes=(64, 32),
            activation="relu",
            solver="adam",  # Adam optimizer
            alpha=0.001,  # Weight decay (L2 penalty)
            max_iter=500,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=42,
        )

    def evaluate(self, ticker: str, candles_data: list) -> Dict[str, Any]:
        """
        Constrói tensores de features, normaliza, treina a rede e infere o próximo passo.
        """
        try:
            if not candles_data or len(candles_data) < 50:
                return {
                    "mlp_score": 0.5,
                    "verdict": "WAIT",
                    "confidence": 0.0,
                    "error": "Dados insuficientes para treino da rede (min: 50).",
                }

            # Montagem do Dataset (Feature Collection)
            X = []
            y = []

            for i in range(3, len(candles_data) - 1):
                c = candles_data[i]
                c_prev1 = candles_data[i - 1]
                c_prev3 = candles_data[i - 3]

                try:
                    close = float(c["close"])
                    high = float(c["high"])
                    low = float(c["low"])
                    prev_close = float(c_prev1["close"])
                    prev3_close = float(c_prev3["close"])

                    if close == 0 or prev_close == 0 or prev3_close == 0:
                        continue

                    # Features: Retorno, Volatilidade (Range), Momentum
                    ret = (close - prev_close) / prev_close
                    vol = (high - low) / close
                    mom = (close - prev3_close) / prev3_close

                    # Target: 1 se a PRÓXIMA barra subir, senão 0
                    next_close = float(candles_data[i + 1]["close"])
                    target = 1 if next_close > close else 0

                    X.append([ret, vol, mom])
                    y.append(target)
                except Exception:
                    continue

            if len(X) < 30:
                return {
                    "mlp_score": 0.5,
                    "verdict": "WAIT",
                    "confidence": 0.0,
                    "error": "Features válidas insuficientes após parse.",
                }

            X = np.array(X)
            y = np.array(y)

            if len(np.unique(y)) < 2:
                return {
                    "mlp_score": 0.5,
                    "verdict": "WAIT",
                    "confidence": 0.0,
                    "error": "Apenas uma classe no target. Rede não pode convergir.",
                }

            # Normalização (Z-Score) -> Sem Data Leakage!
            X_scaled = self.scaler.fit_transform(X)

            # Treinamento On-the-Fly (In-Pipeline Training Engine)
            self.model.fit(X_scaled, y)

            # Predição (Inference) para o momento ATUAL
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

            X_last = np.array([[last_ret, last_vol, last_mom]])
            X_last_scaled = self.scaler.transform(X_last)

            prob_up = self.model.predict_proba(X_last_scaled)[0][1]

            # Decisão Linear
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
                "loss_convergence": "stable"
                if self.model.n_iter_ < self.model.max_iter
                else "unstable",
                "source": "technical_neural",
            }

        except Exception as e:
            logger.error(f"Neural Expert falhou para {ticker}: {e}")
            return {
                "mlp_score": 0.5,
                "verdict": "WAIT",
                "confidence": 0.0,
                "error": str(e),
            }
