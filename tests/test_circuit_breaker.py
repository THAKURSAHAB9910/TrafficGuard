import pytest
import time
from gateway.core.circuit_breaker import CircuitBreakerManager, CircuitState


def test_circuit_breaker_transitions():
    cbm = CircuitBreakerManager(
        failure_threshold=3,
        recovery_timeout=1.0,
        half_open_success_threshold=2
    )

    cb = cbm.get_breaker("backend-1")
    assert cb.state == CircuitState.CLOSED
    assert cbm.can_execute("backend-1") is True

    # 1st failure
    cbm.record_failure("backend-1")
    assert cb.state == CircuitState.CLOSED

    # 2nd failure
    cbm.record_failure("backend-1")
    assert cb.state == CircuitState.CLOSED

    # 3rd failure -> Tripped to OPEN
    cbm.record_failure("backend-1")
    assert cb.state == CircuitState.OPEN
    assert cbm.can_execute("backend-1") is False

    # Simulate waiting past recovery timeout
    cb.open_until = time.time() - 0.1

    # Now can_execute should allow 1 probe request and transition to HALF_OPEN
    assert cbm.can_execute("backend-1") is True
    assert cb.state == CircuitState.HALF_OPEN

    # 1st probe success
    cbm.record_success("backend-1")
    assert cb.state == CircuitState.HALF_OPEN

    # 2nd probe success -> reaches threshold (2) -> transitions to CLOSED!
    cbm.record_success("backend-1")
    assert cb.state == CircuitState.CLOSED
    assert cbm.can_execute("backend-1") is True


def test_circuit_breaker_half_open_failure_reopen():
    cbm = CircuitBreakerManager(
        failure_threshold=2,
        recovery_timeout=1.0,
        half_open_success_threshold=2
    )
    cb = cbm.get_breaker("backend-2")

    # Trip to OPEN
    cbm.record_failure("backend-2")
    cbm.record_failure("backend-2")
    assert cb.state == CircuitState.OPEN

    # Cooldown expires -> probe in HALF_OPEN
    cb.open_until = time.time() - 0.1
    assert cbm.can_execute("backend-2") is True
    assert cb.state == CircuitState.HALF_OPEN

    # Probe request FAILS -> immediately re-trips to OPEN!
    cbm.record_failure("backend-2")
    assert cb.state == CircuitState.OPEN
    assert cbm.can_execute("backend-2") is False
