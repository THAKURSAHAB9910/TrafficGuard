export interface LatencyPercentiles {
  avg: number;
  p50: number;
  p95: number;
  p99: number;
  min: number;
  max: number;
}

export interface MetricsSummary {
  gateway_status: string;
  algorithm: string;
  rate_limiter_algorithm: string;
  metrics: {
    total_requests: number;
    current_rps: number;
    total_successes: number;
    total_client_errors: number;
    total_server_errors: number;
    rate_limit_rejections: number;
    circuit_breaker_rejections: number;
    load_shed_rejections: number;
    error_rate_pct: number;
    latency: LatencyPercentiles;
    backend_routed_counts: Record<string, number>;
    backend_error_counts: Record<string, number>;
  };
  cache: {
    hits: number;
    misses: number;
    bypasses: number;
    total_requests: number;
    hit_rate: number;
    hit_rate_pct: number;
    cached_entries_memory: number;
  };
  circuit_breakers: Record<string, CircuitBreakerInfo>;
  adaptive_controller: Record<string, BackendAdaptiveStats>;
  backends_health: Record<string, BackendHealthInfo>;
}

export interface BackendHealthInfo {
  id: string;
  name: string;
  url: string;
  weight: number;
  is_active: boolean;
  is_healthy: boolean;
  is_routable: boolean;
  is_flapping: boolean;
  flapping_penalty_remaining: number;
  flap_count: number;
  consecutive_successes: number;
  consecutive_failures: number;
  last_latency_ms: number;
  last_error: string | null;
  last_check_time: number;
}

export interface CircuitBreakerInfo {
  backend_id: string;
  state: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  consecutive_failures: number;
  consecutive_successes: number;
  failure_threshold: number;
  recovery_timeout: number;
  retry_after_seconds: number;
  last_state_change: number;
}

export interface AdaptiveDecision {
  backend_id: string;
  timestamp: number;
  action: 'SHED' | 'EXPAND' | 'HOLD' | 'REJECT';
  reason: string;
  observed_p95_ms: number;
  observed_error_rate: number;
  previous_limit: number;
  new_limit: number;
  in_flight: number;
}

export interface BackendAdaptiveStats {
  backend_id: string;
  current_concurrency_limit: number;
  in_flight: number;
  p95_latency_ms: number;
  avg_latency_ms: number;
  error_rate: number;
  total_shed_requests: number;
  recent_decisions: AdaptiveDecision[];
}

export interface BackendNodeAdmin {
  id: string;
  name: string;
  url: string;
  weight: number;
  is_active: boolean;
  is_healthy: boolean;
  is_routable: boolean;
  is_flapping: boolean;
  flapping_penalty_remaining: number;
  circuit_state: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  circuit_retry_after: number;
  active_connections: number;
  total_routed: number;
  dynamic_concurrency_limit: number;
  p95_latency_ms: number;
  error_rate: number;
  last_error: string | null;
}

export interface RequestLog {
  id: string;
  timestamp: number;
  client_ip: string;
  method: string;
  path: string;
  backend_id: string | null;
  status_code: number;
  latency_ms: number;
  cache_status: string;
  algorithm: string | null;
  circuit_state: string | null;
  error: string | null;
}
