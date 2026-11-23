import time
import math
import logging
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
import redis.asyncio as aioredis
from gateway.config import RateLimitAlgorithm, settings

logger = logging.getLogger("trafficguard.rate_limiter")

# Atomic Token Bucket in Redis Lua
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'last_updated')
local tokens = tonumber(data[1])
local last_updated = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_updated = now
else
    local delta = math.max(0, now - last_updated)
    tokens = math.min(capacity, tokens + delta * refill_rate)
end

if tokens >= requested then
    tokens = tokens - requested
    redis.call('HMSET', key, 'tokens', tokens, 'last_updated', now)
    local ttl = math.ceil(capacity / refill_rate) * 2
    redis.call('EXPIRE', key, ttl)
    return {1, math.floor(tokens), 0}
else
    local missing = requested - tokens
    local retry_after = math.ceil(missing / refill_rate)
    redis.call('HMSET', key, 'tokens', tokens, 'last_updated', now)
    local ttl = math.ceil(capacity / refill_rate) * 2
    redis.call('EXPIRE', key, ttl)
    return {0, math.floor(tokens), retry_after}
end
"""

# Atomic Sliding Window Log in Redis Lua
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local member = ARGV[4]

local clear_before = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)
local current_count = redis.call('ZCARD', key)

if current_count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window) * 2)
    local remaining = limit - current_count - 1
    return {1, remaining, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if #oldest > 0 then
        local oldest_time = tonumber(oldest[2])
        retry_after = math.max(1, math.ceil(window - (now - oldest_time)))
    end
    return {0, 0, retry_after}
end
"""


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    retry_after: int  # Seconds to wait before retry
    reset_in: int     # Seconds until full reset


class InMemoryTokenBucket:
    """In-memory fallback for Token Bucket rate limiting."""

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_updated = time.time()

    def consume(self, requested: int = 1) -> Tuple[bool, int, int]:
        now = time.time()
        delta = max(0.0, now - self.last_updated)
        self.tokens = min(float(self.capacity), self.tokens + delta * self.refill_rate)
        self.last_updated = now

        if self.tokens >= requested:
            self.tokens -= requested
            return True, int(self.tokens), 0
        else:
            missing = requested - self.tokens
            retry_after = math.ceil(missing / self.refill_rate)
            return False, int(self.tokens), retry_after


class InMemorySlidingWindow:
    """In-memory fallback for Sliding Window log rate limiting."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window_seconds = window_seconds
        self.timestamps: list[float] = []

    def consume(self) -> Tuple[bool, int, int]:
        now = time.time()
        cutoff = now - self.window_seconds
        self.timestamps = [t for t in self.timestamps if t >= cutoff]

        if len(self.timestamps) < self.limit:
            self.timestamps.append(now)
            remaining = self.limit - len(self.timestamps)
            return True, remaining, 0
        else:
            oldest = self.timestamps[0] if self.timestamps else now
            retry_after = max(1, math.ceil(self.window_seconds - (now - oldest)))
            return False, 0, retry_after


class RateLimiter:
    """
    Central Rate Limiter supporting Token Bucket and Sliding Window algorithms.
    Backed by Redis for distributed deployments, with automatic in-memory fallback.
    """

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        default_algorithm: RateLimitAlgorithm = settings.DEFAULT_RATE_LIMIT_ALGORITHM,
    ):
        self.redis = redis_client
        self.algorithm = default_algorithm
        self._tb_script = None
        self._sw_script = None

        # In-memory fallbacks
        self._memory_token_buckets: Dict[str, InMemoryTokenBucket] = {}
        self._memory_sliding_windows: Dict[str, InMemorySlidingWindow] = {}

    async def init(self) -> None:
        if self.redis:
            try:
                await self.redis.ping()
                self._tb_script = self.redis.register_script(TOKEN_BUCKET_LUA)
                self._sw_script = self.redis.register_script(SLIDING_WINDOW_LUA)
                logger.info("Connected to Redis for distributed rate limiting.")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis ({e}). Using in-memory rate limiting.")
                self.redis = None

    async def check(
        self,
        identifier: str,
        route_prefix: str = "global",
        algorithm: Optional[RateLimitAlgorithm] = None,
        capacity: Optional[int] = None,
        refill_rate: Optional[float] = None,
        window_limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> RateLimitResult:
        algo = algorithm or self.algorithm
        eff_capacity = capacity if capacity is not None else settings.DEFAULT_RATE_LIMIT_CAPACITY
        eff_refill_rate = refill_rate if refill_rate is not None else settings.DEFAULT_RATE_LIMIT_REFILL_RATE
        eff_window_limit = window_limit if window_limit is not None else settings.DEFAULT_SLIDING_WINDOW_LIMIT
        eff_window_seconds = window_seconds if window_seconds is not None else settings.DEFAULT_SLIDING_WINDOW_SECONDS

        key = f"trafficguard:rl:{algo.value}:{route_prefix}:{identifier}"
        now = time.time()

        if algo == RateLimitAlgorithm.TOKEN_BUCKET:
            return await self._check_token_bucket(key, eff_capacity, eff_refill_rate, now)
        else:
            return await self._check_sliding_window(key, eff_window_limit, eff_window_seconds, now)

    async def _check_token_bucket(
        self, key: str, capacity: int, refill_rate: float, now: float
    ) -> RateLimitResult:
        if self.redis and self._tb_script:
            try:
                res = await self._tb_script(
                    keys=[key],
                    args=[capacity, refill_rate, now, 1]
                )
                allowed = bool(res[0])
                remaining = int(res[1])
                retry_after = int(res[2])
                reset_in = math.ceil(capacity / refill_rate)
                return RateLimitResult(allowed, remaining, capacity, retry_after, reset_in)
            except Exception as e:
                logger.warning(f"Redis TokenBucket error: {e}. Falling back to in-memory.")

        # In-memory execution
        if key not in self._memory_token_buckets:
            self._memory_token_buckets[key] = InMemoryTokenBucket(capacity, refill_rate)
        bucket = self._memory_token_buckets[key]
        bucket.capacity = capacity
        bucket.refill_rate = refill_rate

        allowed, remaining, retry_after = bucket.consume(1)
        reset_in = math.ceil(capacity / refill_rate)
        return RateLimitResult(allowed, remaining, capacity, retry_after, reset_in)

    async def _check_sliding_window(
        self, key: str, limit: int, window_seconds: int, now: float
    ) -> RateLimitResult:
        if self.redis and self._sw_script:
            try:
                member = f"{now}-{time.perf_counter()}"
                res = await self._sw_script(
                    keys=[key],
                    args=[limit, window_seconds, now, member]
                )
                allowed = bool(res[0])
                remaining = int(res[1])
                retry_after = int(res[2])
                return RateLimitResult(allowed, remaining, limit, retry_after, window_seconds)
            except Exception as e:
                logger.warning(f"Redis SlidingWindow error: {e}. Falling back to in-memory.")

        # In-memory execution
        if key not in self._memory_sliding_windows:
            self._memory_sliding_windows[key] = InMemorySlidingWindow(limit, window_seconds)
        sw = self._memory_sliding_windows[key]
        sw.limit = limit
        sw.window_seconds = window_seconds

        allowed, remaining, retry_after = sw.consume()
        return RateLimitResult(allowed, remaining, limit, retry_after, window_seconds)
