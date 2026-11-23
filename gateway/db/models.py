from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, Index
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    client_ip = Column(String(45), index=True, nullable=False)
    method = Column(String(10), nullable=False)
    path = Column(String(512), nullable=False)
    target_backend_id = Column(String(64), index=True, nullable=True)
    status_code = Column(Integer, nullable=False)
    latency_ms = Column(Float, nullable=False)
    cache_status = Column(String(16), default="BYPASS")  # HIT, MISS, BYPASS
    load_balancer_algo = Column(String(32), nullable=True)
    circuit_state = Column(String(16), nullable=True)
    error_type = Column(String(64), nullable=True)


class BackendRecord(Base):
    __tablename__ = "backend_records"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    url = Column(String(256), nullable=False)
    weight = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_healthy = Column(Boolean, default=True, nullable=False)
    circuit_state = Column(String(16), default="CLOSED", nullable=False)
    failure_count = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RouteRule(Base):
    __tablename__ = "route_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    path_prefix = Column(String(256), unique=True, nullable=False)
    service_cluster = Column(String(64), default="default", nullable=False)
    rate_limit_rpm = Column(Integer, default=60, nullable=False)
    cache_ttl_seconds = Column(Integer, default=30, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    total_requests = Column(Integer, default=0)
    rps = Column(Float, default=0.0)
    avg_latency_ms = Column(Float, default=0.0)
    p95_latency_ms = Column(Float, default=0.0)
    p99_latency_ms = Column(Float, default=0.0)
    error_rate = Column(Float, default=0.0)
    active_connections = Column(Integer, default=0)
    cache_hit_rate = Column(Float, default=0.0)
