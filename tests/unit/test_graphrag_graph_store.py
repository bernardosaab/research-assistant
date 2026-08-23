from unittest.mock import MagicMock

import pytest

from research_assistant.models import Triple
from research_assistant.variants.graphrag.graph_store import Neo4jGraphStore


@pytest.fixture
def fake_driver(monkeypatch):
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    monkeypatch.setattr(
        "research_assistant.variants.graphrag.graph_store.GraphDatabase.driver",
        lambda uri, auth: driver,
    )
    return driver, session


def test_clear_runs_detach_delete(fake_driver):
    _, session = fake_driver
    store = Neo4jGraphStore("bolt://x", "u", "p")

    store.clear()

    session.run.assert_called_once_with("MATCH (n) DETACH DELETE n")


def test_add_triple_merges_entities_and_relation_with_params(fake_driver):
    _, session = fake_driver
    store = Neo4jGraphStore("bolt://x", "u", "p")

    store.add_triple("Napoleon", "born_in", "Corsica", "https://a.com")

    args, kwargs = session.run.call_args
    assert "MERGE" in args[0]
    assert "RELATION" in args[0]
    assert kwargs == {
        "subject": "Napoleon",
        "object": "Corsica",
        "relation": "born_in",
        "source_url": "https://a.com",
    }


def test_get_all_facts_returns_triples_from_query_results(fake_driver):
    _, session = fake_driver
    record = MagicMock()
    record.data.return_value = {
        "subject": "Napoleon",
        "relation": "born_in",
        "object": "Corsica",
        "source_url": "https://a.com",
    }
    session.run.return_value = [record]
    store = Neo4jGraphStore("bolt://x", "u", "p")

    facts = store.get_all_facts()

    assert facts == [
        Triple(subject="Napoleon", relation="born_in", object="Corsica", source_url="https://a.com")
    ]


def test_get_all_facts_empty_graph_returns_empty_list(fake_driver):
    _, session = fake_driver
    session.run.return_value = []
    store = Neo4jGraphStore("bolt://x", "u", "p")

    assert store.get_all_facts() == []


def test_close_closes_the_driver(fake_driver):
    driver, _ = fake_driver
    store = Neo4jGraphStore("bolt://x", "u", "p")

    store.close()

    driver.close.assert_called_once()
