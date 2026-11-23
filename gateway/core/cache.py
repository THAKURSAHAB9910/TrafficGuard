import time
import json
import hashlib
import logging
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
import redis.asyncio as aioredis
from gateway.config import settings

logger = logging.getLogger("trafficguard.cache")


@dataclass
class CachedResponse:
    status_code: int
    headers: Dict[str, str]
    body: bytes
    created_at: float
    ttl: int

    def is_expired(self) -> bool:
        return time.time() > (self.created_at + self.ttl)


class HttpCacheManager:
    """
    HTTP response caching engine.
    Stores cached responses in Redis (or in-memory fallback), respects Cache-Control,
    and protects private / authenticated endpoints.
    """

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        enabled: bool = settings.CACHE_ENABLED,
        default_ttl: int = settings.CACHE_DEFAULT_TTL_SECONDS,
    ):
        self.redis = redis_client
        self.enabled = enabled
        self.default_ttl = default_ttl

        # In-memory fallback
        self._memory_cache: Dict[str, CachedResponse] = {}

        # Telemetry metrics
        self.hits: int = 0
        self.misses: int = 0
        self.bypasses: int = 0

    def compute_cache_key(self, method: str, path: str, query_params: str = "") -> str:
        raw = f"{method.upper()}:{path}:{query_params}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"trafficguard:cache:{digest}"

    def is_request_cacheable(self, method: str, headers: Dict[str, str]) -> Tuple[bool, str]:
        if not self.enabled:
            return False, "CACHE_DISABLED"

        if method.upper() != "GET":
            return False, "NON_GET_METHOD"

        # Check headers for sensitive/private/auth tokens
        auth_header = headers.get("authorization") or headers.get("Authorization")
        if auth_header:
            return False, "AUTHENTICATED_REQUEST"

        cookie_header = headers.get("cookie") or headers.get("Cookie")
        if cookie_header and ("session" in cookie_header.lower() or "token" in cookie_header.lower()):
            return False, "SESSION_COOKIE_PRESENT"

        cache_control = headers.get("cache-control", "").lower()
        if "no-cache" in cache_control or "no-store" in cache_control:
            return False, "CLIENT_NO_CACHE"

        return True, "ELIGIBLE"

    def is_response_cacheable(self, status_code: int, headers: Dict[str, str], body_len: int) -> bool:
        if status_code != 200:
            return False

        if body_len > settings.CACHE_MAX_PAYLOAD_BYTES:
            return False

        # Header checks
        cc = headers.get("cache-control", "").lower()
        if "private" in cc or "no-store" in cc:
            return False

        if "set-cookie" in headers or "Set-Cookie" in headers:
            return False

        return True

    async def get(self, key: str) -> Optional[CachedResponse]:
        if not self.enabled:
            return None

        # Try Redis
        if self.redis:
            try:
                data = await self.redis.get(key)
                if data:
                    payload = json.loads(data)
                    cached = CachedResponse(
                        status_code=payload["status_code"],
                        headers=payload["headers"],
                        body=bytes.fromhex(payload["body_hex"]),
                        created_at=payload["created_at"],
                        ttl=payload["ttl"],
                    )
                    if not cached.is_expired():
                        self.hits += 1
                        return cached
            except Exception as e:
                logger.warning(f"Redis cache read error: {e}")

        # In-memory fallback
        cached = self._memory_cache.get(key)
        if cached:
            if not cached.is_expired():
                self.hits += 1
                return cached
            else:
                del self._memory_cache[key]

        self.misses += 1
        return None

    async def set(
        self,
        key: str,
        status_code: int,
        headers: Dict[str, str],
        body: bytes,
        ttl: Optional[int] = None,
    ) -> None:
        if not self.enabled:
            return

        effective_ttl = ttl or self.default_ttl
        clean_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in ["content-length", "date", "server", "transfer-encoding", "connection"]
        }

        cached = CachedResponse(
            status_code=status_code,
            headers=clean_headers,
            body=body,
            created_at=time.time(),
            ttl=effective_ttl,
        )

        # Write to Redis
        if self.redis:
            try:
                payload = json.dumps({
                    "status_code": status_code,
                    "headers": clean_headers,
                    "body_hex": body.hex(),
                    "created_at": cached.created_at,
                    "ttl": effective_ttl,
                })
                await self.redis.set(key, payload, ex=effective_ttl)
                return
            except Exception as e:
                logger.warning(f"Redis cache write error: {e}")

        # In-memory fallback
        self._memory_cache[key] = cached

    def record_bypass(self) -> None:
        self.bypasses += 1

    def get_stats(self) -> dict:
        total = self.hits + self.misses
        hit_rate = (self.hits / total) if total > 0 else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "bypasses": self.bypasses,
            "total_requests": total + self.bypasses,
            "hit_rate": round(hit_rate, 4),
            "hit_rate_pct": round(hit_rate * 100.0, 2),
            "cached_entries_memory": len(self._memory_cache),
        }

    def clear(self) -> None:
        self._memory_cache.clear()
        self.hits = 0
        self.misses = 0
        self.bypasses = 0
