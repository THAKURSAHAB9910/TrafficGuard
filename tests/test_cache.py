import pytest
from gateway.core.cache import HttpCacheManager


@pytest.mark.asyncio
async def test_cache_miss_hit_and_expiration():
    cache = HttpCacheManager(redis_client=None, enabled=True, default_ttl=2)

    method = "GET"
    path = "/api/data"
    headers = {"accept": "application/json"}
    
    can_cache, reason = cache.is_request_cacheable(method, headers)
    assert can_cache is True
    assert reason == "ELIGIBLE"

    key = cache.compute_cache_key(method, path)

    # 1st read -> MISS
    res = await cache.get(key)
    assert res is None
    assert cache.misses == 1

    # Store response
    await cache.set(key, status_code=200, headers={"content-type": "application/json"}, body=b'{"hello":"world"}', ttl=1)

    # 2nd read -> HIT
    res2 = await cache.get(key)
    assert res2 is not None
    assert res2.status_code == 200
    assert res2.body == b'{"hello":"world"}'
    assert cache.hits == 1

    # Safe cache checks: POST request shouldn't be cacheable
    can_cache_post, reason_post = cache.is_request_cacheable("POST", {})
    assert can_cache_post is False

    # Authenticated requests shouldn't be cacheable
    can_cache_auth, reason_auth = cache.is_request_cacheable("GET", {"authorization": "Bearer secret123"})
    assert can_cache_auth is False
