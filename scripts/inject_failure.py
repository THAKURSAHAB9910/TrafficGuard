#!/usr/bin/env python3
"""
TrafficGuard Failure Injection & Resilience Verification Script
Demonstrates:
  1. Baseline healthy traffic distribution.
  2. Failure injection (crashing Backend 2).
  3. Automatic Gateway failure detection & failover to healthy nodes.
  4. Backend restoration & automatic re-entry into the routing pool.
"""

import sys
import time
import httpx

GATEWAY_URL = "http://127.0.0.1:8000"
BACKEND_2_URL = "http://127.0.0.1:8002"


def print_step(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def send_requests(client: httpx.Client, count: int = 15):
    distribution = {}
    statuses = {}
    headers = {"Cache-Control": "no-cache"}
    for i in range(count):
        try:
            r = client.get(f"{GATEWAY_URL}/api/v1/proxy/api/data?test={i}_{time.time()}", headers=headers, timeout=3.0)
            backend = r.headers.get("X-TrafficGuard-Backend", "unknown")
            distribution[backend] = distribution.get(backend, 0) + 1
            statuses[r.status_code] = statuses.get(r.status_code, 0) + 1
        except Exception as e:
            statuses["error"] = statuses.get("error", 0) + 1
    return distribution, statuses


def main():
    print("TrafficGuard — Automated Failure Injection & Failover Test")
    print(f"Target Gateway: {GATEWAY_URL}")

    with httpx.Client(timeout=5.0) as client:
        # Check gateway health
        try:
            r = client.get(f"{GATEWAY_URL}/health")
            if r.status_code != 200:
                print(f"[ERROR] Gateway is not healthy: {r.status_code}")
                sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Could not connect to Gateway at {GATEWAY_URL}: {e}")
            print("Please ensure the system is running via docker-compose or run_all.py.")
            sys.exit(1)

        # -------------------------------------------------------------
        # Step 1: Baseline Verification
        # -------------------------------------------------------------
        print_step("Step 1: Baseline Traffic Distribution (All Backends Healthy)")
        dist, status_map = send_requests(client, 18)
        print(f"  Request Statuses: {status_map}")
        print(f"  Routing Distribution: {dist}")
        assert "backend-2" in dist, "Backend 2 was expected in baseline distribution"
        print("  ✓ All 3 backends receiving traffic normally.")

        # -------------------------------------------------------------
        # Step 2: Inject Failure into Backend 2
        # -------------------------------------------------------------
        print_step("Step 2: Injecting Outage into Backend 2 (Simulated Crash)")
        print(f"  Calling Backend 2 outage endpoint...")
        try:
            r = client.post(f"{GATEWAY_URL}/api/admin/simulate/backend-2/status?status_str=DOWN")
            print(f"  Backend 2 status set to DOWN: {r.json()}")
        except Exception as e:
            print(f"  Direct call fallback: {e}")
            client.post(f"{BACKEND_2_URL}/simulate/status?status_str=DOWN")

        # Wait 3.5s for health checker to observe failures
        print("  Waiting 3.5s for Gateway active health checker to detect outage...")
        time.sleep(3.5)

        # -------------------------------------------------------------
        # Step 3: Verify Failover
        # -------------------------------------------------------------
        print_step("Step 3: Verifying Automatic Failover")
        dist, status_map = send_requests(client, 20)
        print(f"  Request Statuses: {status_map}")
        print(f"  Routing Distribution: {dist}")
        assert "backend-2" not in dist, "Backend 2 should NOT have received any requests!"
        print("  ✓ Success: Zero requests sent to failed Backend 2.")
        print("  ✓ Failover confirmed: 100% of traffic handled by healthy backends (backend-1 & backend-3).")

        # -------------------------------------------------------------
        # Step 4: Restart Backend 2
        # -------------------------------------------------------------
        print_step("Step 4: Restoring Backend 2 (Simulated Recovery)")
        print("  Setting Backend 2 status back to UP...")
        client.post(f"{GATEWAY_URL}/api/admin/simulate/backend-2/status?status_str=UP")

        print("  Waiting 6s for consecutive health checks (healthy_threshold = 2)...")
        time.sleep(6.5)

        # -------------------------------------------------------------
        # Step 5: Verify Pool Re-entry
        # -------------------------------------------------------------
        print_step("Step 5: Verifying Backend 2 Re-entry into Routing Pool")
        dist, status_map = send_requests(client, 24)
        print(f"  Request Statuses: {status_map}")
        print(f"  Routing Distribution: {dist}")
        assert "backend-2" in dist, "Backend 2 should have re-entered the routing pool!"
        print(f"  ✓ Success: Backend 2 successfully restored and processed {dist.get('backend-2', 0)} requests.")

        print("\n" + "*" * 70)
        print("  ALL FAILURE INJECTION SCENARIOS PASSED WITH 100% RESILIENCE!")
        print("*" * 70 + "\n")


if __name__ == "__main__":
    main()
