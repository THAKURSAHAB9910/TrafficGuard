import os
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoadBalancerAlgorithm(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"


class RateLimitAlgorithm(str, Enum):
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"


class BackendNode(BaseModel):
    id: str
    name: str
    url: str
    weight: int = 1
    max_concurrency: int = 50
    is_active: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Gateway Networking
    GATEWAY_HOST: str = "0.0.0.0"
    GATEWAY_PORT: int = 8000
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/trafficguard",
        description="PostgreSQL async connection string. Falls back to sqlite+aiosqlite:///trafficguard.db if unavailable."
    )
    SQLITE_FALLBACK_URL: str = "sqlite+aiosqlite:///trafficguard.db"

    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for distributed rate limits and caching."
    )

    # Core Load Balancer Settings
    DEFAULT_ALGORITHM: LoadBalancerAlgorithm = LoadBalancerAlgorithm.ROUND_ROBIN

    # Default Backends
    DEFAULT_BACKENDS: List[BackendNode] = Field(
        default_factory=lambda: [
            BackendNode(
                id="backend-1",
                name="Alpha Service",
                url=os.getenv("BACKEND_1_URL", "http://127.0.0.1:8001"),
                weight=3,
                max_concurrency=50
            ),
            BackendNode(
                id="backend-2",
                name="Beta Service",
                url=os.getenv("BACKEND_2_URL", "http://127.0.0.1:8002"),
                weight=2,
                max_concurrency=40
            ),
            BackendNode(
                id="backend-3",
                name="Gamma Service",
                url=os.getenv("BACKEND_3_URL", "http://127.0.0.1:8003"),
                weight=1,
                max_concurrency=25
            ),
        ]
    )

    # Health Checking
    HEALTH_CHECK_INTERVAL_SECONDS: float = 3.0
    HEALTH_CHECK_TIMEOUT_SECONDS: float = 1.5
    HEALTHY_THRESHOLD: int = 2
    UNHEALTHY_THRESHOLD: int = 3
    FLAPPING_WINDOW_SECONDS: float = 60.0
    FLAPPING_THRESHOLD_FLIPS: int = 3
    FLAPPING_PENALTY_SECONDS: float = 30.0

    # Rate Limiting Defaults
    DEFAULT_RATE_LIMIT_ALGORITHM: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    DEFAULT_RATE_LIMIT_CAPACITY: int = 30  # Max burst tokens
    DEFAULT_RATE_LIMIT_REFILL_RATE: float = 10.0  # Tokens per second
    DEFAULT_SLIDING_WINDOW_LIMIT: int = 60  # Requests per minute
    DEFAULT_SLIDING_WINDOW_SECONDS: int = 60

    # Circuit Breaker Defaults
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 4  # Consecutive failures to trip
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: float = 8.0  # Seconds to stay OPEN before HALF-OPEN
    CIRCUIT_BREAKER_HALF_OPEN_SUCCESS_THRESHOLD: int = 3  # Successes required in HALF-OPEN to CLOSE
    CIRCUIT_BREAKER_FAILURE_RATE_THRESHOLD: float = 0.5  # 50% failure rate over window

    # Adaptive Concurrency Controller Defaults
    ADAPTIVE_TARGET_LATENCY_MS: float = 120.0
    ADAPTIVE_MAX_LATENCY_MS: float = 350.0
    ADAPTIVE_MIN_CONCURRENCY: int = 4
    ADAPTIVE_INITIAL_CONCURRENCY: int = 30
    ADAPTIVE_MAX_CONCURRENCY: int = 150
    ADAPTIVE_BACKOFF_FACTOR: float = 0.7
    ADAPTIVE_INCREASE_STEP: int = 1
    ADAPTIVE_ERROR_RATE_THRESHOLD: float = 0.15

    # Caching Defaults
    CACHE_ENABLED: bool = True
    CACHE_DEFAULT_TTL_SECONDS: int = 30
    CACHE_MAX_PAYLOAD_BYTES: int = 1024 * 1024  # 1MB

    # Client Request Timeout
    PROXY_TIMEOUT_SECONDS: float = 4.0


settings = Settings()
