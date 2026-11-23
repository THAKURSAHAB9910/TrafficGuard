import pytest
from gateway.config import BackendNode, LoadBalancerAlgorithm
from gateway.core.load_balancer import LoadBalancer


def test_round_robin_distribution():
    lb = LoadBalancer(default_algorithm=LoadBalancerAlgorithm.ROUND_ROBIN)
    backends = [
        BackendNode(id="b1", name="B1", url="http://b1", weight=1),
        BackendNode(id="b2", name="B2", url="http://b2", weight=1),
        BackendNode(id="b3", name="B3", url="http://b3", weight=1),
    ]

    selected = [lb.select_backend(backends).id for _ in range(6)]
    assert selected == ["b1", "b2", "b3", "b1", "b2", "b3"]


def test_least_connections_distribution():
    lb = LoadBalancer(default_algorithm=LoadBalancerAlgorithm.LEAST_CONNECTIONS)
    backends = [
        BackendNode(id="b1", name="B1", url="http://b1", weight=1),
        BackendNode(id="b2", name="B2", url="http://b2", weight=1),
    ]

    # Initially both 0, picks b1
    first = lb.select_backend(backends)
    assert first.id == "b1"
    lb.increment_active_connection("b1")

    # Now b1 has 1 active, b2 has 0 -> should pick b2
    second = lb.select_backend(backends)
    assert second.id == "b2"
    lb.increment_active_connection("b2")

    # Both have 1 active -> pick b1 or b2
    lb.decrement_active_connection("b1")
    # Now b1 has 0, b2 has 1 -> should pick b1
    third = lb.select_backend(backends)
    assert third.id == "b1"


def test_smooth_weighted_round_robin_distribution():
    lb = LoadBalancer(default_algorithm=LoadBalancerAlgorithm.WEIGHTED_ROUND_ROBIN)
    # Weights: b1: 5, b2: 1, b3: 1 -> total 7. Over 7 requests, b1 gets 5, b2 gets 1, b3 gets 1
    backends = [
        BackendNode(id="b1", name="B1", url="http://b1", weight=5),
        BackendNode(id="b2", name="B2", url="http://b2", weight=1),
        BackendNode(id="b3", name="B3", url="http://b3", weight=1),
    ]

    counts = {"b1": 0, "b2": 0, "b3": 0}
    for _ in range(70):
        node = lb.select_backend(backends)
        counts[node.id] += 1

    assert counts["b1"] == 50
    assert counts["b2"] == 10
    assert counts["b3"] == 10
