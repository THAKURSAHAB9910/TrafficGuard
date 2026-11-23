import asyncio
import pytest
from gateway.config import BackendNode, LoadBalancerAlgorithm
from gateway.core.load_balancer import LoadBalancer
from gateway.core.circuit_breaker import CircuitBreakerManager


@pytest.mark.asyncio
async def test_concurrent_request_tracking_least_connections():
    """Verify that under concurrent load, Least Connections correctly balances requests."""
    lb = LoadBalancer(default_algorithm=LoadBalancerAlgorithm.LEAST_CONNECTIONS)
    b1 = BackendNode(id="b1", name="B1", url="http://b1")
    b2 = BackendNode(id="b2", name="B2", url="http://b2")
    backends = [b1, b2]

    # Simulate 10 concurrent requests
    async def worker(task_id: int):
        node = lb.select_backend(backends)
        lb.increment_active_connection(node.id)
        # Hold in-flight for a moment
        await asyncio.sleep(0.02)
        lb.decrement_active_connection(node.id)
        return node.id

    tasks = [worker(i) for i in range(10)]
    results = await asyncio.gather(*tasks)

    # Both nodes should have received work roughly equally
    b1_count = results.count("b1")
    b2_count = results.count("b2")
    assert b1_count > 0
    assert b2_count > 0
    assert abs(b1_count - b2_count) <= 2
    # All connections should be cleanly released back to 0
    assert lb.get_active_connections("b1") == 0
    assert lb.get_active_connections("b2") == 0


@pytest.mark.asyncio
async def test_concurrent_circuit_breaker_tripping():
    """Verify thread-safe circuit breaker tripping under concurrent failures."""
    cbm = CircuitBreakerManager(failure_threshold=5, recovery_timeout=2.0)

    async def fail_task():
        cbm.record_failure("b1")

    # Fire 10 concurrent failures
    await asyncio.gather(*[fail_task() for _ in range(10)])

    cb = cbm.get_breaker("b1")
    assert cb.state.value == "OPEN"
    assert cbm.can_execute("b1") is False
