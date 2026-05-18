import numpy as np
from datetime import datetime
from typing import Dict, Any


class QuantumWalkBias:
    """
    Discrete Quantum Random Walk on a circular state space.

    Uses Hadamard coin operator + cyclic shift operator on a complex
    state vector of dimension 2^n_qubits to produce a probability
    distribution. Samples from that distribution to derive a small
    stochastic bias for pricing models.
    """

    def __init__(self, n_qubits: int = 4):
        self.n_qubits = n_qubits

    def run_simulation(self) -> Dict[str, Any]:
        """
        Simula a execução de uma Caminhada Quântica Discreta (QRW) no tempo no espaço
        circular de dimensão 2^n_qubits usando o operador de moeda Hadamard.
        """
        try:
            n_positions = 2**self.n_qubits

            # Inicializa estado quântico complexo: (coin_state, position)
            # coin_state: 0 (up), 1 (down)
            psi = np.zeros((2, n_positions), dtype=complex)

            # Estado inicial simétrico localizado na posição 0 para espalhar uniformemente
            psi[0, 0] = 1.0 / np.sqrt(2)
            psi[1, 0] = 1j / np.sqrt(2)

            # Executa passos da Caminhada Quântica
            steps = 12
            for _ in range(steps):
                # 1. Aplica a moeda Hadamard em cada posição
                # H = [[1, 1], [1, -1]] / sqrt(2)
                psi_new = np.zeros_like(psi)
                psi_new[0, :] = (psi[0, :] + psi[1, :]) / np.sqrt(2)
                psi_new[1, :] = (psi[0, :] - psi[1, :]) / np.sqrt(2)

                # 2. Operador de deslocamento (Shift)
                # Coin 0 desloca para a esquerda (passo -1)
                # Coin 1 desloca para a direita (passo +1)
                psi[0, :] = np.roll(psi_new[0, :], -1)
                psi[1, :] = np.roll(psi_new[1, :], 1)

            # Calcula a distribuição de probabilidade de medição (quadrado do módulo da amplitude)
            prob = np.abs(psi[0, :]) ** 2 + np.abs(psi[1, :]) ** 2
            prob /= np.sum(prob)  # Garante normalização unitária

            # Amostra 1000 'shots' com base na distribuição quântica obtida
            shots = 1000
            sampled_indices = np.random.choice(n_positions, size=shots, p=prob)

            counts = {}
            for idx in sampled_indices:
                # Converte o índice posicional para representação binária de n_qubits
                binary_state = format(idx, f"0{self.n_qubits}b")
                counts[binary_state] = counts.get(binary_state, 0) + 1

            return {
                "counts": counts,
                "timestamp": datetime.now().isoformat(),
                "status": "Discrete quantum random walk on circle complete",
                "qubits": self.n_qubits,
            }
        except Exception as e:
            return {"error": str(e), "counts": {}}

    def sample_bias(self) -> float:
        """Stochastic bias in [-0.05, 0.05] from quantum walk amplitude sampling."""
        res = self.run_simulation()
        if "error" in res:
            return 0.0

        # Usa a proporção de estados '1' para gerar um ruído quântico
        c = res["counts"]
        total = sum(c.values())
        ones = c.get("1" * self.n_qubits, 0)

        # Converte para um valor entre -0.05 e 0.05
        bias = (ones / total - 0.5) * 0.1
        return float(bias)
