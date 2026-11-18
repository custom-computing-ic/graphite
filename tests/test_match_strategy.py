import pytest

from heterograph import HGraph

import graphite.match_strategy as matching
from graphite import IsoMatchStrategy


def symmetric_pairs():
    graph = HGraph()
    graph.add_vx(4)
    for source, target in [(0, 1), (2, 3)]:
        graph.add_edge(source, target)
    return graph


@pytest.fixture(autouse=True)
def duplicate_isomorphisms(monkeypatch):
    original = matching.subgraph_isomorphism

    def duplicates(*args, **kwargs):
        for mapping in original(*args, **kwargs):
            yield mapping
            yield mapping

    monkeypatch.setattr(matching, "subgraph_isomorphism", duplicates)


def test_max_n_stops_enumerating_after_enough_matches(monkeypatch):
    graph = symmetric_pairs()
    original = matching.subgraph_isomorphism
    consumed = []

    def tracked(*args, **kwargs):
        for mapping in original(*args, **kwargs):
            consumed.append(1)
            yield mapping

    monkeypatch.setattr(matching, "subgraph_isomorphism", tracked)
    results, _ = IsoMatchStrategy().find_matches(
        g=graph, select="a => b", deduplicate=False, max_n=1
    )
    assert len(results) == 1
    assert len(consumed) == 1


def test_limit_counts_unique_matches_only():
    graph = symmetric_pairs()
    strategy = IsoMatchStrategy()
    all_matches, _ = strategy.find_matches(g=graph, select="a => b", deduplicate=False)
    unique, _ = strategy.find_matches(g=graph, select="a => b", max_n=2)
    assert len(all_matches) == 4
    assert len(unique) == 2
    assert {frozenset(match.values()) for match in unique} == {
        frozenset((0, 1)), frozenset((2, 3))
    }


def test_limit_applies_after_where_filter():
    graph = symmetric_pairs()
    strategy = IsoMatchStrategy()
    all_matches, _ = strategy.find_matches(g=graph, select="a => b", deduplicate=False)
    chosen = all_matches[-1]
    accepted, _ = strategy.find_matches(
        g=graph, select="a => b", deduplicate=False, max_n=1,
        where=lambda g, a, b: (a, b) == (chosen["a"], chosen["b"]),
    )
    assert accepted == [chosen]


def test_zero_limit_returns_all_matches():
    graph = symmetric_pairs()
    results, _ = IsoMatchStrategy().find_matches(
        g=graph, select="a => b", deduplicate=False, max_n=0
    )
    assert len(results) == 4
