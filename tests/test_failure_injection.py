import pytest
import time
from gateway.config import BackendNode, LoadBalancerAlgorithm
from gateway.core.load_balancer import LoadBalancer
from gateway.core.health_checker import HealthChecker


def test_failure_injection_failover_and_recovery():
    """
    Scenario:
      1. Initialize 3 backends (b1, b2, b3).
      2. Verify all 3 receive traffic under Round Robin.
      3. Inject failure into b2 (3 consecutive failures).
      4. Verify gateway removes b2 from the routable candidate pool.
      5. Verify requests continue seamlessly across b1 and b3 (failover).
      6. Restore b2 (2 consecutive successful health checks).
      7. Verify b2 re-enters the active routing pool and receives traffic.
    """
    b1 = BackendNode(id="b1", name="Alpha", url="http://127.0.0.1:8001", weight=1)
    b2 = BackendNode(id="b2", name="Beta", url="http://127.0.0.1:8002", weight=1)
    b3 = BackendNode(id="b3", name="Gamma", url="http://127.0.0.1:8003", weight=1)

    lb = LoadBalancer(default_algorithm=LoadBalancerAlgorithm.ROUND_ROBIN)
    checker = HealthChecker(
        backends=[b1, b2, b3],
        healthy_threshold=2,
        unhealthy_threshold=3,
        flapping_window=10.0,
        flapping_threshold=5,
        flapping_penalty=2.0,
    )

    # 1. Initial State: All 3 healthy
    routable = checker.get_routable_backends()
    assert len(routable) == 3
    selected = [lb.select_backend(routable).id for _ in range(6)]
    assert selected == ["b1", "b2", "b3", "b1", "b2", "b3"]

    # 2. Inject Failure into b2: 3 failures reach unhealthy_threshold
    checker.record_failure("b2", "Simulated Crash")
    checker.record_failure("b2", "Simulated Crash")
    checker.record_failure("b2", "Simulated Crash")

    # 3. Verify failure detection
    assert checker.is_routable("b2") is False
    assert checker.states["b2"].is_healthy is False

    # 4. Verify Automatic Failover: candidate pool has only b1 and b3
    routable_after_fail = checker.get_routable_backends()
    assert len(routable_after_fail) == 2
    assert {b.id for b in routable_after_fail} == {"b1", "b3"}

    # Requests continue cleanly without b2
    routed_failover = [lb.select_backend(routable_after_fail).id for _ in range(4)]
    assert "b2" not in routed_failover
    assert routed_failover == ["b1", "b3", "b1", "b3"]

    # 5. Restore Backend b2: 1st success (threshold is 2, so not yet active)
    checker.record_success("b2", latency_ms=15.0)
    assert checker.is_routable("b2") is False

    # 6. 2nd success: meets healthy_threshold -> RECOVERED!
    checker.record_success("b2", latency_ms=14.0)
    assert checker.is_routable("b2") is True
    assert checker.states["b2"].is_healthy is True

    # 7. Verify b2 has re-entered the routing pool
    routable_restored = checker.get_routable_backends()
    assert len(routable_restored) == 3
    routed_restored = [lb.select_backend(routable_restored).id for _ in range(6)]
    assert "b2" in routed_restored
    assert set(routed_restored) == {"b1", "b2", "b3"}
