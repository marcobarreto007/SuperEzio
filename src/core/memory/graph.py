"""Knowledge Graph — Fase 4: Entidades e relações GraphRAG.

Implementa grafo de conhecimento para conectar memórias por entidades:
- tickers, experts, regimes, verdicts, datas
- relacionamentos entre memórias
- GraphRAG traversal para busca contextual

Técnicas 2026:
- Entidades: extração automática de textos
- Relações: graph edges com pesos
- Traversal: shortest path, neighborhood queries
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """Entidade no grafo de conhecimento."""

    id: str  # "ticker:AAPL", "expert:fundamental", "verdict:BUY"
    type: str  # "ticker", "expert", "regime", "verdict", "date"
    name: str  # "AAPL", "fundamental", "BULLISH", "2026-06-14"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Relation:
    """Relação entre entidades."""

    source: str  # Entity ID
    target: str  # Entity ID
    type: str  # "mentions", "analyzed_by", "resulted_in", "on_date"
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphNode:
    """Nó no grafo (entidade + conexões)."""

    entity: Entity
    outgoing: list[Relation] = field(default_factory=list)
    incoming: list[Relation] = field(default_factory=list)


class KnowledgeGraph:
    """Grafo de conhecimento para memórias.

    Conecta entidades como tickers, experts, verdicts através de
    relações extraídas das memórias conversacionais e trades.
    """

    def __init__(self):
        self._nodes: dict[str, GraphNode] = {}
        self._entity_index: dict[str, set[str]] = defaultdict(set)  # type -> entity_ids

    def add_entity(self, entity: Entity) -> None:
        """Add entity to graph."""
        if entity.id not in self._nodes:
            self._nodes[entity.id] = GraphNode(entity=entity)
            self._entity_index[entity.type].add(entity.id)

    def add_relation(self, relation: Relation) -> None:
        """Add relation between entities."""
        # Ensure entities exist
        if relation.source not in self._nodes:
            self.add_entity(Entity(id=relation.source, type="unknown", name=relation.source))
        if relation.target not in self._nodes:
            self.add_entity(Entity(id=relation.target, type="unknown", name=relation.target))

        # Add edges
        self._nodes[relation.source].outgoing.append(relation)
        self._nodes[relation.target].incoming.append(relation)

    def get_entity(self, entity_id: str) -> Entity | None:
        """Get entity by ID."""
        node = self._nodes.get(entity_id)
        return node.entity if node else None

    def get_neighbors(
        self,
        entity_id: str,
        direction: str = "outgoing",
        edge_type: str | None = None,
    ) -> list[tuple[str, float]]:
        """Get neighboring entities.

        Args:
            entity_id: Source entity ID
            direction: "outgoing", "incoming", or "both"
            edge_type: Filter by relation type

        Returns:
            List of (neighbor_id, weight) tuples
        """
        if entity_id not in self._nodes:
            return []

        node = self._nodes[entity_id]
        neighbors = []

        if direction in ("outgoing", "both"):
            for rel in node.outgoing:
                if edge_type is None or rel.type == edge_type:
                    neighbors.append((rel.target, rel.weight))

        if direction in ("incoming", "both"):
            for rel in node.incoming:
                if edge_type is None or rel.type == edge_type:
                    neighbors.append((rel.source, rel.weight))

        return neighbors

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 3,
    ) -> list[str] | None:
        """Find shortest path between entities using BFS.

        Returns:
            List of entity IDs from source to target, or None if no path
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return None

        if source_id == target_id:
            return [source_id]

        from collections import deque

        queue = deque([(source_id, [source_id])])
        visited = {source_id}

        while queue:
            current, path = queue.popleft()

            if len(path) > max_depth:
                continue

            for neighbor, _ in self.get_neighbors(current):
                if neighbor == target_id:
                    return path + [neighbor]

                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None

    def get_entities_by_type(self, entity_type: str) -> list[Entity]:
        """Get all entities of a given type."""
        return [self._nodes[eid].entity for eid in self._entity_index.get(entity_type, set())]

    def query_context(
        self,
        entity_ids: list[str],
        max_hops: int = 2,  # noqa: ARG001 — reserved for future graph traversal depth
    ) -> dict[str, Any]:
        """Query contextual neighborhood for entities.

        Args:
            entity_ids: Starting entity IDs
            max_hops: Maximum traversal depth

        Returns:
            Dict with entities, relations, and paths found
        """
        context = {
            "entities": {},
            "relations": [],
            "paths": [],
        }

        visited = set(entity_ids)

        # Collect direct neighbors
        for eid in entity_ids:
            if eid not in self._nodes:
                continue

            entity = self._nodes[eid].entity
            context["entities"][eid] = {
                "id": entity.id,
                "type": entity.type,
                "name": entity.name,
                "metadata": entity.metadata,
            }

            # Outgoing relations
            for neighbor, weight in self.get_neighbors(eid, direction="outgoing"):
                if neighbor not in visited:
                    visited.add(neighbor)
                    neighbor_entity = self._nodes[neighbor].entity
                    context["entities"][neighbor] = {
                        "id": neighbor_entity.id,
                        "type": neighbor_entity.type,
                        "name": neighbor_entity.name,
                        "metadata": neighbor_entity.metadata,
                    }

                context["relations"].append(
                    {
                        "source": eid,
                        "target": neighbor,
                        "weight": weight,
                    }
                )

        return context


class EntityExtractor:
    """Extract entities from text (memories, trades)."""

    # Common ticker patterns
    TICKER_PATTERN = r"\b([A-Z]{1,5})\b"

    # Verdict keywords
    VERDICTS = {
        "buy",
        "sell",
        "hold",
        "strong_buy",
        "strong_sell",
        "bullish",
        "bearish",
        "neutral",
        "candidate",
    }

    # Expert types
    EXPERTS = {
        "fundamental",
        "technical",
        "sentiment",
        "macro",
    }

    # Regime keywords
    REGIMES = {
        "bull",
        "bear",
        "sideways",
        "volatile",
        "trending",
    }

    def extract_from_text(self, text: str, doc_id: str) -> list[Entity]:
        """Extract entities from text.

        Returns:
            List of Entity objects
        """
        text_lower = text.lower()
        entities = []

        # Extract tickers (ALL CAPS words)
        for match in re.finditer(self.TICKER_PATTERN, text):
            ticker = match.group(1)
            # Filter common non-ticker words
            if ticker not in {"THE", "AND", "FOR", "WITH", "FROM"}:
                entities.append(
                    Entity(
                        id=f"ticker:{ticker}",
                        type="ticker",
                        name=ticker,
                        metadata={"source_doc": doc_id},
                    )
                )

        # Extract verdicts
        for verdict in self.VERDICTS:
            if verdict in text_lower:
                entities.append(
                    Entity(
                        id=f"verdict:{verdict}",
                        type="verdict",
                        name=verdict.upper(),
                        metadata={"source_doc": doc_id},
                    )
                )

        # Extract experts
        for expert in self.EXPERTS:
            if expert in text_lower:
                entities.append(
                    Entity(
                        id=f"expert:{expert}",
                        type="expert",
                        name=expert,
                        metadata={"source_doc": doc_id},
                    )
                )

        # Extract regimes
        for regime in self.REGIMES:
            if regime in text_lower:
                entities.append(
                    Entity(
                        id=f"regime:{regime}",
                        type="regime",
                        name=regime.upper(),
                        metadata={"source_doc": doc_id},
                    )
                )

        return entities


class GraphMemoryBridge:
    """Bridge entre memórias e grafo de conhecimento.

    Ingere ConversationMemory e PaperJournal no grafo,
    permitindo queries contextuais.
    """

    def __init__(self, graph: KnowledgeGraph | None = None):
        self._graph = graph or KnowledgeGraph()
        self._extractor = EntityExtractor()

    def ingest_conversation_turn(self, turn) -> None:
        """Ingest conversation turn into graph."""
        doc_id = f"conv_{turn.session_id}_{turn.timestamp}"

        # Extract entities
        text = f"{turn.user_message} {turn.bob_response}"
        entities = self._extractor.extract_from_text(text, doc_id)

        # Add entities to graph
        doc_entity = Entity(
            id=doc_id,
            type="conversation",
            name=f"Conversation {turn.timestamp[:10]}",
            metadata={"session_id": turn.session_id, "ticker": turn.ticker_discussed},
        )
        self._graph.add_entity(doc_entity)

        for entity in entities:
            self._graph.add_entity(entity)
            # Connect to doc
            self._graph.add_relation(
                Relation(
                    source=doc_id,
                    target=entity.id,
                    type="mentions",
                    weight=1.0,
                )
            )

        # Connect ticker if discussed
        if turn.ticker_discussed:
            ticker_id = f"ticker:{turn.ticker_discussed}"
            ticker_entity = Entity(
                id=ticker_id,
                type="ticker",
                name=turn.ticker_discussed,
            )
            self._graph.add_entity(ticker_entity)
            self._graph.add_relation(
                Relation(
                    source=doc_id,
                    target=ticker_id,
                    type="discusses",
                    weight=1.0,
                )
            )

            # Connect verdict if present
            if turn.verdict:
                verdict_id = f"verdict:{turn.verdict.lower()}"
                self._graph.add_entity(
                    Entity(
                        id=verdict_id,
                        type="verdict",
                        name=turn.verdict.upper(),
                    )
                )
                self._graph.add_relation(
                    Relation(
                        source=ticker_id,
                        target=verdict_id,
                        type="resulted_in",
                        weight=1.0,
                    )
                )

    def ingest_paper_trade(self, trade: dict) -> None:
        """Ingest paper trade into graph."""
        trade_id = trade.get("trade_id", f"trade_{trade.get('ticker', 'unknown')}")

        # Trade entity
        trade_entity = Entity(
            id=trade_id,
            type="paper_trade",
            name=f"{trade.get('direction', '').upper()} {trade.get('ticker', 'UNKNOWN')}",
            metadata={
                "entry_price": trade.get("entry_price"),
                "exit_price": trade.get("exit_price"),
                "pnl": trade.get("pnl_amount"),
            },
        )
        self._graph.add_entity(trade_entity)

        # Ticker connection
        ticker = trade.get("ticker", "").upper()
        if ticker:
            ticker_id = f"ticker:{ticker}"
            self._graph.add_entity(
                Entity(
                    id=ticker_id,
                    type="ticker",
                    name=ticker,
                )
            )
            self._graph.add_relation(
                Relation(
                    source=trade_id,
                    target=ticker_id,
                    type="trades",
                    weight=1.0,
                )
            )

            # Outcome connection
            outcome = trade.get("outcome", "")
            if outcome:
                outcome_id = f"outcome:{outcome.lower()}"
                self._graph.add_entity(
                    Entity(
                        id=outcome_id,
                        type="outcome",
                        name=outcome.upper(),
                    )
                )
                self._graph.add_relation(
                    Relation(
                        source=trade_id,
                        target=outcome_id,
                        type="resulted_in",
                        weight=1.0,
                    )
                )

    def query_ticker_context(self, ticker: str) -> dict[str, Any]:
        """Query all context for a ticker."""
        ticker_id = f"ticker:{ticker.upper()}"
        return self._graph.query_context([ticker_id], max_hops=2)

    def get_graph(self) -> KnowledgeGraph:
        """Get underlying graph."""
        return self._graph

    def format_graph_context(self, context: dict[str, Any]) -> str:
        """Format graph query result as text."""
        if not context.get("entities"):
            return "[GRAPH] No graph context found."

        lines = ["[GRAPH_MEMORY] — Knowledge graph connections:"]
        lines.append(f"\nEntities: {len(context['entities'])}")

        # Group by type
        by_type: dict[str, list[str]] = defaultdict(list)
        for eid, entity in context["entities"].items():
            by_type[entity["type"]].append(entity["name"])

        for entity_type, names in sorted(by_type.items()):
            lines.append(f"\n{entity_type.upper()}: {', '.join(set(names))}")

        # Relations
        if context["relations"]:
            lines.append(f"\nRelations: {len(context['relations'])}")

        return "\n".join(lines)


# Singleton
_graph_bridge: GraphMemoryBridge | None = None


def reset_graph_bridge() -> None:
    """Reset singleton (for testing)."""
    global _graph_bridge
    _graph_bridge = None


def get_graph_bridge() -> GraphMemoryBridge:
    """Get singleton GraphMemoryBridge."""
    global _graph_bridge
    if _graph_bridge is None:
        _graph_bridge = GraphMemoryBridge()
        logger.info("GraphMemoryBridge initialized")
    return _graph_bridge
