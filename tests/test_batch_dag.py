"""DAG topological sort + cycle detection."""

import pytest

from swarm.batch.dag import DependencyGraph
from swarm.core.errors import PlanValidationError


def test_topological_order_linear():
    g = DependencyGraph({"a": set(), "b": {"a"}, "c": {"b"}})
    assert g.topological_order() == ["a", "b", "c"]


def test_topological_order_diamond():
    g = DependencyGraph(
        {"a": set(), "b": {"a"}, "c": {"a"}, "d": {"b", "c"}}
    )
    order = g.topological_order()
    assert order.index("a") < order.index("b")
    assert order.index("a") < order.index("c")
    assert order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")


def test_cycle_detection():
    g = DependencyGraph({"a": {"b"}, "b": {"a"}})
    with pytest.raises(PlanValidationError):
        g.topological_order()


def test_iter_layers():
    g = DependencyGraph(
        {"a": set(), "b": set(), "c": {"a", "b"}, "d": {"c"}}
    )
    layers = list(g.iter_layers())
    assert layers == [["a", "b"], ["c"], ["d"]] or layers == [["b", "a"], ["c"], ["d"]]


def test_validate_unknown_dep():
    g = DependencyGraph({"a": {"missing"}})
    errors = g.validate()
    assert errors and "missing" in errors[0]
