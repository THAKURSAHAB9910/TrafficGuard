import pytest
import time
from gateway.config import RateLimitAlgorithm
from gateway.core.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_token_bucket_rate_limiter():
    limiter = RateLimiter(redis_client=None, default_algorithm=RateLimitAlgorithm.TOKEN_BUCKET)
    await limiter.init()

    # Capacity = 3, refill_rate = 1 token/sec
    client_ip = "192.168.1.100"
    
    # 1st request -> allowed
    res1 = await limiter.check(client_ip, capacity=3, refill_rate=1.0)
    assert res1.allowed is True
    assert res1.remaining == 2

    # 2nd request -> allowed
    res2 = await limiter.check(client_ip, capacity=3, refill_rate=1.0)
    assert res2.allowed is True
    assert res2.remaining == 1

    # 3rd request -> allowed
    res3 = await limiter.check(client_ip, capacity=3, refill_rate=1.0)
    assert res3.allowed is True
    assert res3.remaining == 0

    # 4th request -> blocked (429)
    res4 = await limiter.check(client_ip, capacity=3, refill_rate=1.0)
    assert res4.allowed is False
    assert res4.retry_after >= 1


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter():
    limiter = RateLimiter(redis_client=None, default_algorithm=RateLimitAlgorithm.SLIDING_WINDOW)
    await limiter.init()

    client_ip = "192.168.1.200"
    # Limit = 2 per 5 seconds
    res1 = await limiter.check(client_ip, algorithm=RateLimitAlgorithm.SLIDING_WINDOW, window_limit=2, window_seconds=5)
    assert res1.allowed is True

    res2 = await limiter.check(client_ip, algorithm=RateLimitAlgorithm.SLIDING_WINDOW, window_limit=2, window_seconds=5)
    assert res2.allowed is True

    res3 = await limiter.check(client_ip, algorithm=RateLimitAlgorithm.SLIDING_WINDOW, window_limit=2, window_seconds=5)
    assert res3.allowed is False
    assert res3.retry_after >= 1
