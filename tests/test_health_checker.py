import pytest
import time
from gateway.config import BackendNode
from gateway.core.health_checker import HealthChecker


def test_health_checker_state_transitions():
    b1 = BackendNode(id="b1", name="B1", url="http://127.0.0.1:8001", weight=1)
    checker = HealthChecker(
        backends=[b1],
        healthy_threshold=2,
        unhealthy_threshold=3,
        flapping_window=10.0,
        flapping_threshold=4,
        flapping_penalty=5.0
    )

    # Initially healthy
    assert checker.is_routable("b1") is True

    # 1st failure: still healthy
    checker.record_failure("b1", "HTTP 500")
    assert checker.is_routable("b1") is True

    # 2nd failure: still healthy
    checker.record_failure("b1", "HTTP 500")
    assert checker.is_routable("b1") is True

    # 3rd failure: reaches unhealthy threshold (3) -> becomes UNHEALTHY
    checker.record_failure("b1", "HTTP 500")
    assert checker.is_routable("b1") is False

    # 1st success: not yet restored (requires 2)
    checker.record_success("b1", latency_ms=10.0)
    assert checker.is_routable("b1") is False

    # 2nd success: reaches healthy threshold (2) -> becomes HEALTHY again!
    checker.record_success("b1", latency_ms=10.0)
    assert checker.is_routable("b1") is True


def test_health_checker_flapping_detection():
    b1 = BackendNode(id="b1", name="B1", url="http://127.0.0.1:8001", weight=1)
    # Flapping threshold: 3 flips within 10s triggers 2.0s penalty
    checker = HealthChecker(
        backends=[b1],
        healthy_threshold=1,
        unhealthy_threshold=1,
        flapping_window=10.0,
        flapping_threshold=3,
        flapping_penalty=2.0
    )

    # Flip 1: Healthy -> Unhealthy
    checker.record_failure("b1", "Fail")
    assert checker.states["b1"].is_healthy is False

    # Flip 2: Unhealthy -> Healthy
    checker.record_success("b1", 10.0)
    assert checker.states["b1"].is_healthy is True

    # Flip 3: Healthy -> Unhealthy (triggers FLAPPING)
    checker.record_failure("b1", "Fail")
    state = checker.states["b1"]
    assert state.is_flapping is True

    # Even if healthy_threshold is met now, node stays quarantined (not routable)
    checker.record_success("b1", 10.0)
    assert checker.is_routable("b1") is False
    assert checker.states["b1"].is_flapping is True

    # Fast forward past penalty time
    checker.states["b1"].flapping_penalty_until = time.time() - 0.1
    # Check flapping clears and restores routability
    checker.record_success("b1", 10.0)
    assert checker.states["b1"].is_flapping is False
    assert checker.is_routable("b1") is True
