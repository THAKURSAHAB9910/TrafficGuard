"""
TrafficGuard Locust Load Testing Suite
Simulates realistic concurrent client traffic through the TrafficGuard API Gateway.
"""

from locust import HttpUser, task, between, events
import random


class TrafficGuardUser(HttpUser):
    # Wait between 50ms and 250ms between requests
    wait_time = between(0.05, 0.25)

    @task(6)
    def fetch_data(self):
        """Standard cacheable GET data request (common traffic)."""
        category = random.choice(["analytics", "users", "finance", "telemetry"])
        self.client.get(
            f"/api/v1/proxy/api/data?category={category}",
            name="/proxy/api/data [Cacheable]",
        )

    @task(3)
    def compute_workload(self):
        """Dynamic computation request with varying iterations."""
        difficulty = random.choice([5000, 10000, 25000])
        self.client.get(
            f"/api/v1/proxy/api/compute?iterations={difficulty}",
            name="/proxy/api/compute [CPU Heavy]",
        )

    @task(1)
    def echo_payload(self):
        """POST request with JSON payload to test header and body preservation."""
        self.client.post(
            "/api/v1/proxy/api/echo",
            json={"client_uuid": "locust-worker", "timestamp": 123456789},
            name="/proxy/api/echo [POST]",
        )
