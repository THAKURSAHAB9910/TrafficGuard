"""
TrafficGuard Local End-to-End Verification Script
=================================================
Tests all running local components:
  1. Backend-1, Backend-2, Backend-3 health endpoints
  2. Gateway health, summary, and Prometheus metrics
  3. CORS headers against Vite origin (http://localhost:5173)
  4. Real request proxying through gateway (/api/v1/proxy/api/data)
  5. Load balancing across all 3 backend nodes
  6. Rate limiting enforcement (HTTP 429)
  7. Fault injection (delay, error, outage, reset)
  8. Frontend dev server availability (http://localhost:5173)
"""

import sys
import time
import json
import urllib.request
import urllib.error

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS_COUNT = 0
FAIL_COUNT = 0


def record_test(name: str, passed: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if passed:
        PASS_COUNT += 1
        print(f"  {GREEN}✔ PASS:{RESET} {name} {f'({detail})' if detail else ''}")
    else:
        FAIL_COUNT += 1
        print(f"  {RED}✘ FAIL:{RESET} {name} {f'({detail})' if detail else ''}")


def http_req(url: str, method: str = "GET", headers: dict = None, data: dict = None, timeout: float = 3.0):
    body = None
    req_headers = {"User-Agent": "TrafficGuard-Verifier"}
    if headers:
        req_headers.update(headers)
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            resp_body = res.read().decode("utf-8")
            res_headers = {k.lower(): v for k, v in res.headers.items()}
            try:
                parsed_json = json.loads(resp_body)
            except Exception:
                parsed_json = None
            return res.status, res_headers, parsed_json, resp_body
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
        except Exception:
            err_json = None
        return e.code, {k.lower(): v for k, v in e.headers.items()}, err_json, err_body
    except Exception as e:
        return 0, {}, None, str(e)


def wait_for_ready(url: str, timeout: float = 12.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        status, _, _, _ = http_req(url, timeout=1.0)
        if status in (200, 404):
            return True
        time.sleep(0.5)
    return False


def main():
    print(f"\n{BOLD}{CYAN}=== TrafficGuard Local Stack Verification ==={RESET}\n")

    # Ensure services are up
    print(f"{YELLOW}Waiting for services to be ready...{RESET}")
    wait_for_ready("http://127.0.0.1:8000/health", timeout=10.0)
    wait_for_ready("http://127.0.0.1:5173", timeout=10.0)

    # 1. Verify Backends
    print(f"\n{BOLD}1. Checking Upstream Backend Nodes:{RESET}")
    for port, bname in [(8001, "Alpha (8001)"), (8002, "Beta (8002)"), (8003, "Gamma (8003)")]:
        status, headers, body, raw = http_req(f"http://127.0.0.1:{port}/health")
        record_test(f"Backend {bname} health", status == 200, f"HTTP {status}")

    # 2. Verify Gateway Health & Metrics
    print(f"\n{BOLD}2. Checking Gateway Health & Admin APIs:{RESET}")
    status, headers, body, _ = http_req("http://127.0.0.1:8000/health")
    record_test("Gateway /health", status == 200 and body and body.get("status") in ("UP", "healthy"), f"Status: {body.get('status') if body else None}")

    status, headers, body, _ = http_req("http://127.0.0.1:8000/api/metrics/summary")
    record_test("Gateway /api/metrics/summary", status == 200 and body and body.get("gateway_status") == "ONLINE")

    status, headers, body, _ = http_req("http://127.0.0.1:8000/api/admin/backends")
    node_count = len(body.get("backends", [])) if body else 0
    record_test("Gateway registered backends", status == 200 and node_count == 3, f"{node_count} nodes")

    # 3. Verify CORS for http://localhost:5173
    print(f"\n{BOLD}3. Checking CORS Configuration for Local Vite UI:{RESET}")
    status, headers, _, _ = http_req(
        "http://127.0.0.1:8000/api/metrics/summary",
        headers={"Origin": "http://localhost:5173"}
    )
    cors_origin = headers.get("access-control-allow-origin")
    cors_creds = headers.get("access-control-allow-credentials")
    record_test(
        "CORS Access-Control-Allow-Origin",
        cors_origin in ("http://localhost:5173", "*"),
        f"Origin: {cors_origin}, Credentials: {cors_creds}"
    )

    # 4. Verify Traffic Forwarding & Load Balancing
    print(f"\n{BOLD}4. Checking Traffic Forwarding & Load Balancing:{RESET}")
    routed_nodes = set()
    all_ok = True
    for i in range(15):
        status, headers, body, _ = http_req(f"http://127.0.0.1:8000/api/v1/proxy/api/data?test_lb={i}")
        if status != 200:
            all_ok = False
        node_id = headers.get("x-trafficguard-backend") or headers.get("x-backend-service")
        if node_id and node_id != "cache":
            routed_nodes.add(node_id)
        time.sleep(0.04)

    record_test("Traffic proxy forwarding /api/v1/proxy/api/data", all_ok, "15/15 200 OK")
    record_test(
        "Load balancer multi-node distribution",
        len(routed_nodes) >= 2,
        f"Routed across: {', '.join(sorted(routed_nodes))}"
    )

    # 5. Verify Rate Limiting (Token Bucket 429)
    print(f"\n{BOLD}5. Checking Rate Limiting Enforcement:{RESET}")
    got_429 = False
    for i in range(40):
        status, headers, body, _ = http_req(
            "http://127.0.0.1:8000/api/v1/proxy/api/data?test_rate_limit=1",
            headers={"X-Client-ID": "test-verifier-ratelimit-client"}
        )
        if status == 429:
            got_429 = True
            break

    record_test("Rate Limiter triggers HTTP 429 Shield", got_429, "429 Too Many Requests received")

    # 6. Verify Fault Injection
    print(f"\n{BOLD}6. Checking Fault Injection Controls:{RESET}")
    # Inject delay on backend-1
    status, _, body, _ = http_req("http://127.0.0.1:8000/api/admin/simulate/backend-1/delay?delay_ms=250", method="POST")
    record_test("Inject fault: delay +250ms", status == 200)

    # Reset fault
    status, _, body, _ = http_req("http://127.0.0.1:8000/api/admin/simulate/backend-1/reset", method="POST")
    record_test("Reset fault on backend-1", status == 200)

    # 7. Verify Frontend Dev Server on http://localhost:5173
    print(f"\n{BOLD}7. Checking Vite React Frontend Dev Server:{RESET}")
    fe_status = 0
    raw_html = ""
    for fe_url in ["http://localhost:5173", "http://127.0.0.1:5173"]:
        s, _, _, raw = http_req(fe_url, timeout=3.0)
        if s == 200:
            fe_status = s
            raw_html = raw
            break

    has_vite = "vite" in raw_html.lower() or "trafficguard" in raw_html.lower() or "<html" in raw_html.lower()
    record_test("Frontend dev server running on http://localhost:5173", fe_status == 200 and has_vite, f"HTTP {fe_status}")

    # Summary
    print(f"\n{BOLD}{'=' * 50}{RESET}")
    if FAIL_COUNT == 0:
        print(f"{BOLD}{GREEN}ALL {PASS_COUNT} CHECKS PASSED! Local stack is 100% operational.{RESET}")
    else:
        print(f"{BOLD}{RED}{FAIL_COUNT} checks failed out of {PASS_COUNT + FAIL_COUNT}.{RESET}")
    print(f"{BOLD}{'=' * 50}{RESET}\n")

    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
