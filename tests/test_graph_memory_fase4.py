"""Tests for Knowledge Graph - Fase 4: Entidades e relações GraphRAG."""

import sys
from pathlib import Path

# Add src to path for pytest
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from dataclasses import dataclass

from core.memory.graph import (
    Entity,
    EntityExtractor,
    GraphMemoryBridge,
    KnowledgeGraph,
    Relation,
    get_graph_bridge,
    reset_graph_bridge,
)


@dataclass
class MockTurn:
    """Mock ConversationTurn for testing."""
    session_id: str = "test_session"
    timestamp: str = "2026-06-14T10:00:00"
    user_message: str = "Analyze AAPL stock"
    bob_response: str = "AAPL looks bullish"
    ticker_discussed: str = "AAPL"
    verdict: str = "BUY"
    confidence: float = 0.8
    category: str = "analysis"


class TestKnowledgeGraph:
    """Test knowledge graph operations."""

    def test_graph_empty(self):
        """Test empty graph."""
        graph = KnowledgeGraph()
        assert len(graph._nodes) == 0

    def test_add_entity(self):
        """Test adding entities."""
        graph = KnowledgeGraph()
        entity = Entity(
            id="ticker:AAPL",
            type="ticker",
            name="AAPL",
        )
        graph.add_entity(entity)

        assert len(graph._nodes) == 1
        assert graph.get_entity("ticker:AAPL") is not None

    def test_add_relation(self):
        """Test adding relations."""
        graph = KnowledgeGraph()
        graph.add_entity(Entity(id="e1", type="test", name="E1"))
        graph.add_entity(Entity(id="e2", type="test", name="E2"))

        relation = Relation(source="e1", target="e2", type="connects")
        graph.add_relation(relation)

        neighbors = graph.get_neighbors("e1")
        assert len(neighbors) == 1
        assert neighbors[0] == ("e2", 1.0)

    def test_get_neighbors_directions(self):
        """Test get_neighbors with different directions."""
        graph = KnowledgeGraph()
        graph.add_entity(Entity(id="a", type="test", name="A"))
        graph.add_entity(Entity(id="b", type="test", name="B"))
        graph.add_entity(Entity(id="c", type="test", name="C"))

        graph.add_relation(Relation(source="a", target="b", type="out"))
        graph.add_relation(Relation(source="c", target="a", type="in"))

        # Outgoing from A
        out = graph.get_neighbors("a", direction="outgoing")
        assert len(out) == 1
        assert out[0] == ("b", 1.0)

        # Incoming to A
        inc = graph.get_neighbors("a", direction="incoming")
        assert len(inc) == 1
        assert inc[0] == ("c", 1.0)

        # Both
        both = graph.get_neighbors("a", direction="both")
        assert len(both) == 2

    def test_find_path(self):
        """Test finding shortest path."""
        graph = KnowledgeGraph()
        # Create chain: A -> B -> C
        for eid in ["a", "b", "c"]:
            graph.add_entity(Entity(id=eid, type="test", name=eid.upper()))

        graph.add_relation(Relation(source="a", target="b", type="path"))
        graph.add_relation(Relation(source="b", target="c", type="path"))

        path = graph.find_path("a", "c")
        assert path == ["a", "b", "c"]

    def test_find_path_no_connection(self):
        """Test path finding with no connection."""
        graph = KnowledgeGraph()
        graph.add_entity(Entity(id="a", type="test", name="A"))
        graph.add_entity(Entity(id="b", type="test", name="B"))

        path = graph.find_path("a", "b")
        assert path is None

    def test_find_path_max_depth(self):
        """Test path finding with max depth limit."""
        graph = KnowledgeGraph()
        # Long chain
        for i in range(10):
            graph.add_entity(Entity(id=f"n{i}", type="test", name=f"N{i}"))

        for i in range(9):
            graph.add_relation(Relation(source=f"n{i}", target=f"n{i+1}", type="chain"))

        # Should not find path with max_depth=3
        path = graph.find_path("n0", "n9", max_depth=3)
        assert path is None

        # Should find with max_depth=10
        path = graph.find_path("n0", "n9", max_depth=10)
        assert path is not None
        assert len(path) == 10

    def test_get_entities_by_type(self):
        """Test filtering entities by type."""
        graph = KnowledgeGraph()
        graph.add_entity(Entity(id="t1", type="ticker", name="AAPL"))
        graph.add_entity(Entity(id="t2", type="ticker", name="TSLA"))
        graph.add_entity(Entity(id="v1", type="verdict", name="BUY"))

        tickers = graph.get_entities_by_type("ticker")
        assert len(tickers) == 2
        assert all(e.type == "ticker" for e in tickers)

    def test_query_context(self):
        """Test contextual neighborhood query."""
        graph = KnowledgeGraph()
        # Create star: center connected to A, B, C
        graph.add_entity(Entity(id="center", type="test", name="CENTER"))
        for eid in ["a", "b", "c"]:
            graph.add_entity(Entity(id=eid, type="test", name=eid.upper()))
            graph.add_relation(Relation(source="center", target=eid, type="star"))

        context = graph.query_context(["center"], max_hops=1)

        assert len(context["entities"]) == 4  # center + 3 neighbors
        assert len(context["relations"]) == 3

    def test_query_context_empty(self):
        """Test query with non-existent entities."""
        graph = KnowledgeGraph()
        context = graph.query_context(["nonexistent"])
        assert context["entities"] == {}
        assert context["relations"] == []


class TestEntityExtractor:
    """Test entity extraction from text."""

    def test_extract_tickers(self):
        """Test ticker extraction."""
        extractor = EntityExtractor()
        text = "I think AAPL and TSLA are good buys."
        entities = extractor.extract_from_text(text, "doc1")

        ticker_ids = {e.id for e in entities if e.type == "ticker"}
        assert "ticker:AAPL" in ticker_ids
        assert "ticker:TSLA" in ticker_ids

    def test_extract_verdicts(self):
        """Test verdict extraction."""
        extractor = EntityExtractor()
        text = "This is a bullish setup, I'm buying."
        entities = extractor.extract_from_text(text, "doc1")

        verdict_ids = {e.id for e in entities if e.type == "verdict"}
        assert "verdict:bullish" in verdict_ids

    def test_extract_experts(self):
        """Test expert type extraction."""
        extractor = EntityExtractor()
        text = "According to the fundamental expert..."
        entities = extractor.extract_from_text(text, "doc1")

        expert_ids = {e.id for e in entities if e.type == "expert"}
        assert "expert:fundamental" in expert_ids

    def test_extract_regimes(self):
        """Test regime extraction."""
        extractor = EntityExtractor()
        text = "Market is in a bull regime."
        entities = extractor.extract_from_text(text, "doc1")

        regime_ids = {e.id for e in entities if e.type == "regime"}
        assert "regime:bull" in regime_ids

    def test_extract_filters_common_words(self):
        """Test common words are filtered from tickers."""
        extractor = EntityExtractor()
        text = "THE AND FOR WITH are not tickers."
        entities = extractor.extract_from_text(text, "doc1")

        tickers = [e for e in entities if e.type == "ticker"]
        assert len(tickers) == 0


class TestGraphMemoryBridge:
    """Test bridge between memories and graph."""

    def test_ingest_conversation_turn(self):
        """Test ingesting conversation turn."""
        bridge = GraphMemoryBridge()
        turn = MockTurn(
            user_message="What about AAPL?",
            bob_response="AAPL looks bullish, strong buy candidate.",
            ticker_discussed="AAPL",
            verdict="BUY",
        )

        bridge.ingest_conversation_turn(turn)

        # Check entities created
        graph = bridge.get_graph()
        assert graph.get_entity("ticker:AAPL") is not None
        assert graph.get_entity("verdict:buy") is not None

        # Check relations
        neighbors = graph.get_neighbors("ticker:AAPL")
        assert len(neighbors) > 0

    def test_ingest_paper_trade(self):
        """Test ingesting paper trade."""
        bridge = GraphMemoryBridge()
        trade = {
            "trade_id": "trade_001",
            "ticker": "NVDA",
            "direction": "long",
            "entry_price": 100.0,
            "exit_price": 120.0,
            "outcome": "win",
        }

        bridge.ingest_paper_trade(trade)

        graph = bridge.get_graph()
        assert graph.get_entity("trade_001") is not None
        assert graph.get_entity("ticker:NVDA") is not None
        assert graph.get_entity("outcome:win") is not None

    def test_query_ticker_context(self):
        """Test querying ticker context."""
        bridge = GraphMemoryBridge()
        turn = MockTurn(
            user_message="Analyze AAPL",
            bob_response="Bullish setup",
            ticker_discussed="AAPL",
            verdict="BUY",
        )

        bridge.ingest_conversation_turn(turn)
        context = bridge.query_ticker_context("AAPL")

        assert len(context["entities"]) > 0
        assert "ticker:AAPL" in context["entities"]

    def test_format_graph_context(self):
        """Test formatting graph context."""
        bridge = GraphMemoryBridge()
        turn = MockTurn(ticker_discussed="AAPL")

        bridge.ingest_conversation_turn(turn)
        context = bridge.query_ticker_context("AAPL")

        formatted = bridge.format_graph_context(context)
        assert "[GRAPH_MEMORY]" in formatted
        assert "Entities:" in formatted

    def test_format_empty_context(self):
        """Test formatting empty graph context."""
        bridge = GraphMemoryBridge()
        formatted = bridge.format_graph_context({"entities": {}, "relations": []})
        assert "No graph context" in formatted


def test_graph_bridge_singleton():
    """Test singleton pattern."""
    reset_graph_bridge()

    b1 = get_graph_bridge()
    b2 = get_graph_bridge()

    assert b1 is b2


def test_graph_bridge_reset():
    """Test reset function."""
    b1 = get_graph_bridge()
    reset_graph_bridge()

    b2 = get_graph_bridge()

    assert b1 is not b2
