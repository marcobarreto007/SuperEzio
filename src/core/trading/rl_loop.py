"""RL Loop - Q-learning simplificado para decisões de trading.

Bob usa aprendizado por reforço simplificado para melhorar decisões:
- Estados: contexto de mercado (setup quality, market phase, etc.)
- Ações: BUY, WAIT, REJECT, SIZE_ADJUST
- Recompensas: XP + PnL - Dor

Q-learning é simplificado: não usa deep learning, apenas tabela Q
com dimensões reduzidas para viabilidade prática.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from collections import defaultdict

logger = logging.getLogger(__name__)

DEFAULT_RL_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "rl_log.jsonl"
)


class Action(Enum):
    """Ações que Bob pode tomar."""
    BUY = "BUY"
    WAIT = "WAIT"
    REJECT = "REJECT"
    SIZE_SMALL = "SIZE_SMALL"
    SIZE_NORMAL = "SIZE_NORMAL"
    SIZE_LARGE = "SIZE_LARGE"
    HOLD = "HOLD"
    SELL = "SELL"


class StateFeature(Enum):
    """Features que definem o estado."""
    # Setup quality
    CONFIDENCE_HIGH = "confidence_high"
    CONFIDENCE_MEDIUM = "confidence_medium"
    CONFIDENCE_LOW = "confidence_low"

    # Market phase
    MARKET_BULL = "market_bull"
    MARKET_BEAR = "market_bear"
    MARKET_SIDEWAYS = "market_sideways"

    # Time of day
    MORNING = "morning"
    MIDDAY = "midday"
    CLOSE = "close"

    # Recent performance
    WIN_STREAK = "win_streak"
    LOSS_STREAK = "loss_streak"
    NEUTRAL = "neutral"

    # Pain memory
    HIGH_PAIN_SIMILAR = "high_pain_similar"
    LOW_PAIN_SIMILAR = "low_pain_similar"


@dataclass
class QValue:
    """Valor Q para um par (estado, ação)."""
    state_id: str
    action: Action
    value: float  # Valor Q esperado
    visits: int  # Quantas vezes este estado-ação foi visitado
    last_updated: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "action": self.action.value,
            "value": round(self.value, 3),
            "visits": self.visits,
            "last_updated": self.last_updated,
        }


@dataclass
class RLEpisode:
    """Um episódio de aprendizado (trade completo)."""
    episode_id: str
    timestamp: str
    state_id: str
    action: Action
    reward: float
    next_state_id: str | None = None
    done: bool = False
    trade_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "timestamp": self.timestamp,
            "state_id": self.state_id,
            "action": self.action.value,
            "reward": round(self.reward, 3),
            "next_state_id": self.next_state_id,
            "done": self.done,
            "trade_id": self.trade_id,
            "context": self.context,
        }


class RLLoop:
    """Loop de aprendizado por reforço simplificado."""

    def __init__(
        self,
        log_path: Path | None = None,
        learning_rate: float = 0.1,  # Alpha
        discount_factor: float = 0.9,  # Gamma
        exploration_rate: float = 0.1,  # Epsilon
        exploration_decay: float = 0.995,  # Decaimento de epsilon
    ):
        self._log_path = log_path or DEFAULT_RL_LOG_PATH
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        self._alpha = learning_rate
        self._gamma = discount_factor
        self._epsilon = exploration_rate
        self._epsilon_decay = exploration_decay

        # Tabela Q: dict[state_id][action] = QValue
        self._q_table: dict[str, dict[Action, QValue]] = defaultdict(lambda: defaultdict(lambda: None))  # type: ignore

        # Histórico de episódios
        self._episodes: list[RLEpisode] = []

    def _generate_episode_id(self) -> str:
        """Gera ID único para episódio."""
        return f"ep_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{len(self._episodes)}"

    def _save_episode(self, episode: RLEpisode) -> None:
        """Salva episódio no disco (append-only)."""
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(episode.to_dict(), ensure_ascii=False) + "\n")

    def _encode_state(self, context: dict[str, Any]) -> str:
        """Codifica contexto em um state_id simplificado.

        Args:
            context: Dict com features do estado

        Returns:
            String representando o estado (ex: "high_conf_bull_morning_win_streak")
        """
        features = []

        # Confidence
        confidence = context.get("confidence", 0)
        if confidence >= 0.7:
            features.append("high_conf")
        elif confidence >= 0.5:
            features.append("med_conf")
        else:
            features.append("low_conf")

        # Market trend
        trend = context.get("market_trend", "sideways").lower()
        if "bull" in trend or "up" in trend:
            features.append("bull")
        elif "bear" in trend or "down" in trend:
            features.append("bear")
        else:
            features.append("sideways")

        # Time of day
        hour = context.get("hour", 12)
        if 9 <= hour < 12:
            features.append("morning")
        elif 12 <= hour < 15:
            features.append("midday")
        else:
            features.append("close")

        # Recent streak
        streak = context.get("streak", 0)
        if streak > 2:
            features.append("win_streak")
        elif streak < -2:
            features.append("loss_streak")
        else:
            features.append("neutral")

        # Pain similar
        pain_risk = context.get("pain_risk", "low")
        if pain_risk == "high":
            features.append("high_pain")
        else:
            features.append("low_pain")

        return "_".join(features)

    def get_q_value(self, state_id: str, action: Action) -> float:
        """Retorna valor Q para um par estado-ação."""
        q_entry = self._q_table[state_id][action]
        if q_entry is None:
            # Inicializar com 0
            self._q_table[state_id][action] = QValue(
                state_id=state_id,
                action=action,
                value=0.0,
                visits=0,
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
            return 0.0
        return q_entry.value

    def update_q_value(
        self,
        state_id: str,
        action: Action,
        reward: float,
        next_state_id: str | None = None,
        done: bool = False,
    ) -> None:
        """Atualiza valor Q usando Q-learning update rule.

        Q(s,a) <- Q(s,a) + alpha * (reward + gamma * max_a' Q(s',a') - Q(s,a))

        Args:
            state_id: Estado atual
            action: Ação tomada
            reward: Recompensa recebida
            next_state_id: Próximo estado (None se terminal)
            done: Se episódio terminou
        """
        current_q = self.get_q_value(state_id, action)

        # Calcular target
        if done or next_state_id is None:
            target = reward
        else:
            # max Q value para próximo estado
            next_max = max(
                self.get_q_value(next_state_id, a)
                for a in Action
            )
            target = reward + self._gamma * next_max

        # Q-learning update
        new_q = current_q + self._alpha * (target - current_q)

        # Atualizar tabela
        q_entry = self._q_table[state_id][action]
        if q_entry is None:
            self._q_table[state_id][action] = QValue(
                state_id=state_id,
                action=action,
                value=new_q,
                visits=1,
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
        else:
            q_entry.value = new_q
            q_entry.visits += 1
            q_entry.last_updated = datetime.now(timezone.utc).isoformat()

    def choose_action(
        self,
        context: dict[str, Any],
        available_actions: list[Action] | None = None,
        explore: bool | None = None,
    ) -> Action:
        """Escolhe ação usando epsilon-greedy policy.

        Args:
            context: Contexto atual do estado
            available_actions: Ações disponíveis (padrão: todas)
            explore: Se None, usa self._epsilon

        Returns:
            Ação escolhida
        """
        state_id = self._encode_state(context)
        actions = available_actions or [Action.BUY, Action.WAIT, Action.REJECT]

        # Epsilon-greedy: explorar com probabilidade epsilon
        should_explore = explore if explore is not None else (hash(state_id) % 100 < self._epsilon * 100)

        if should_explore:
            # Explorar: ação aleatória
            import random
            action = random.choice(actions)
            logger.debug("Exploring: chose %s for state %s", action.value, state_id)
            return action

        # Exploitar: melhor ação segundo Q-table
        best_action = None
        best_q = float("-inf")

        for a in actions:
            q_value = self.get_q_value(state_id, a)
            if q_value > best_q:
                best_q = q_value
                best_action = a

        # Se todos Q values são 0 (estado nunca visitado), escolher WAIT por segurança
        if best_action is None or best_q == 0:
            best_action = Action.WAIT

        logger.debug("Exploiting: chose %s (Q=%.2f) for state %s", best_action.value, best_q, state_id)
        return best_action

    def record_episode(
        self,
        context: dict[str, Any],
        action: Action,
        reward: float,
        next_context: dict[str, Any] | None = None,
        done: bool = False,
        trade_id: str | None = None,
    ) -> RLEpisode:
        """Registra um episódio completo e atualiza Q-table.

        Args:
            context: Contexto do estado
            action: Ação tomada
            reward: Recompensa recebida
            next_context: Próximo contexto (None se terminal)
            done: Se episódio terminou
            trade_id: ID do trade relacionado

        Returns:
            Episódio registrado
        """
        state_id = self._encode_state(context)
        next_state_id = self._encode_state(next_context) if next_context else None

        episode = RLEpisode(
            episode_id=self._generate_episode_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            state_id=state_id,
            action=action,
            reward=reward,
            next_state_id=next_state_id,
            done=done,
            trade_id=trade_id,
            context=context,
        )

        # Atualizar Q-table
        self.update_q_value(state_id, action, reward, next_state_id, done)

        # Salvar episódio
        self._episodes.append(episode)
        self._save_episode(episode)

        # Decaimento de epsilon
        self._epsilon = max(0.01, self._epsilon * self._epsilon_decay)

        logger.info(
            "RL Episode: state=%s action=%s reward=%.2f epsilon=%.3f",
            state_id,
            action.value,
            reward,
            self._epsilon,
        )

        return episode

    def calculate_reward(
        self,
        outcome: str,
        pnl_amount: float | None = None,
        confidence: float | None = None,
        pain_score: float = 0.0,
    ) -> float:
        """Calcula recompensa para um outcome.

        Args:
            outcome: "win", "loss", "breakeven"
            pnl_amount: Valor PnL
            confidence: Confiança na entrada
            pain_score: Score de dor (0-1)

        Returns:
            Recompensa (positivo = bom, negativo = ruim)
        """
        reward = 0.0

        if outcome == "win":
            # Win: recompensa base
            reward = 1.0

            # Bonus por PnL
            if pnl_amount and pnl_amount > 0:
                reward += min(2.0, pnl_amount / 100)  # Até +2 por $100

            # Bonus por confiança justificada
            if confidence and confidence >= 0.7:
                reward += 0.5

        elif outcome == "loss":
            # Loss: punição base
            reward = -1.0

            # Punição por PnL
            if pnl_amount and pnl_amount < 0:
                loss_punishment = min(-3.0, pnl_amount / 50)  # Até -3 por $150
                reward += loss_punishment

            # Punição por overconfidence
            if confidence and confidence >= 0.7:
                reward -= 0.5

            # Dor extra
            reward -= pain_score * 2.0

        else:  # breakeven
            reward = 0.0

        return reward

    def get_policy(self, state_id: str | None = None) -> dict[str, Any]:
        """Retorna política atual (melhores ações por estado).

        Args:
            state_id: Se None, retorna política para todos estados

        Returns:
            Dict com policy
        """
        if state_id:
            state_actions = {}
            for action in Action:
                q_entry = self._q_table[state_id][action]
                if q_entry:
                    state_actions[action.value] = round(q_entry.value, 3)
            return {"state_id": state_id, "actions": state_actions}

        # Política para todos estados
        policy = {}
        for s_id, actions_dict in self._q_table.items():
            best_action = None
            best_q = float("-inf")

            for action, q_entry in actions_dict.items():
                if q_entry and q_entry.value > best_q:
                    best_q = q_entry.value
                    best_action = action

            if best_action:
                policy[s_id] = {
                    "best_action": best_action.value,
                    "best_q": round(best_q, 3),
                    "visits": sum(
                        q.visits for q in actions_dict.values() if q
                    ),
                }

        return policy

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do RL loop."""
        if not self._episodes:
            return {
                "total_episodes": 0,
                "unique_states": 0,
                "avg_reward": 0,
                "epsilon": self._epsilon,
            }

        total_rewards = sum(e.reward for e in self._episodes)
        avg_reward = total_rewards / len(self._episodes)

        return {
            "total_episodes": len(self._episodes),
            "unique_states": len(self._q_table),
            "avg_reward": round(avg_reward, 3),
            "epsilon": round(self._epsilon, 4),
            "learning_rate": self._alpha,
            "discount_factor": self._gamma,
        }

    def render_for_bob(self, max_chars: int = 600) -> str:
        """Renderiza insights de RL para o prompt do Bob."""
        if not self._episodes:
            return ""

        stats = self.get_stats()
        lines = [
            "\n=== REINFORCEMENT LEARNING ===",
            f"Episódios: {stats['total_episodes']}",
            f"Estados únicos: {stats['unique_states']}",
            f"Recompensa média: {stats['avg_reward']:.2f}",
            f"Exploração (ε): {stats['epsilon']:.3f}",
        ]

        # Top aprendizados
        policy = self.get_policy()
        top_states = sorted(
            policy.items(),
            key=lambda x: x[1].get("visits", 0),
            reverse=True,
        )[:3]

        if top_states:
            lines.append("\nTop aprendizados:")
            for state_id, info in top_states:
                lines.append(f"- {state_id}: {info['best_action']} (Q={info['best_q']:.2f})")

        lines.append("=== FIM RL ===\n")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n..."

        return result


# Singleton
_rl_loop: RLLoop | None = None


def get_rl_loop() -> RLLoop:
    """Retorna singleton de RLLoop."""
    global _rl_loop
    if _rl_loop is None:
        _rl_loop = RLLoop()
        logger.info("RLLoop initialized")
    return _rl_loop


if __name__ == "__main__":
    # Test mode
    rl = get_rl_loop()

    # Simular alguns episódios
    contexts = [
        {"confidence": 0.8, "market_trend": "bull", "hour": 10, "streak": 1, "pain_risk": "low"},
        {"confidence": 0.6, "market_trend": "bear", "hour": 14, "streak": -1, "pain_risk": "high"},
        {"confidence": 0.9, "market_trend": "bull", "hour": 11, "streak": 3, "pain_risk": "low"},
    ]

    for i, ctx in enumerate(contexts):
        action = rl.choose_action(ctx)
        reward = 1.0 if i % 2 == 0 else -1.0
        rl.record_episode(ctx, action, reward, contexts[min(i + 1, len(contexts) - 1)])

    stats = rl.get_stats()
    print(f"Episodes: {stats['total_episodes']}")
    print(f"Avg reward: {stats['avg_reward']}")
    print(f"\n{rl.render_for_bob()}")
