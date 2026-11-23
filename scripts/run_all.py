#!/usr/bin/env python3
"""
TrafficGuard Local Development & Demonstration Launcher
Orchestrates:
  - Backend 1 (Alpha) on port 8001
  - Backend 2 (Beta)  on port 8002
  - Backend 3 (Gamma) on port 8003
  - Gateway Reverse Proxy on port 8000
  - Dashboard (Vite preview or dev) on port 3000
"""

import os
import sys
import time
import subprocess
import signal

processes = []


def cleanup():
    print("\nShutting down TrafficGuard processes...")
    for p in processes:
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    print("All processes stopped.")


def main():
    print("=" * 70)
    print("  TRAFFICGUARD — PLATFORM ORCHESTRATOR")
    print("=" * 70)

    # 1. Start Backends
    for port, sid, name in [
        (8001, "backend-1", "Alpha Service"),
        (8002, "backend-2", "Beta Service"),
        (8003, "backend-3", "Gamma Service"),
    ]:
        env = os.environ.copy()
        env["PORT"] = str(port)
        env["SERVICE_ID"] = sid
        env["SERVICE_NAME"] = name

        cmd = [sys.executable, "-m", "uvicorn", "backends.server:app", "--port", str(port), "--host", "127.0.0.1", "--log-level", "warning"]
        print(f"[STARTING] {name} ({sid}) on http://127.0.0.1:{port}...")
        p = subprocess.Popen(cmd, env=env)
        processes.append(p)

    time.sleep(1.5)

    # 2. Start Gateway
    cmd_gw = [sys.executable, "-m", "uvicorn", "gateway.main:app", "--port", "8000", "--host", "127.0.0.1", "--log-level", "info"]
    print("[STARTING] TrafficGuard Gateway on http://127.0.0.1:8000...")
    p_gw = subprocess.Popen(cmd_gw)
    processes.append(p_gw)

    time.sleep(1.5)

    # 3. Start Dashboard
    dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard")
    cmd_dash = "npm run dev" if os.name != "nt" else "npm.cmd run dev"
    print(f"[STARTING] React Dashboard in {dashboard_dir} on http://localhost:3000...")
    p_dash = subprocess.Popen(cmd_dash, shell=True, cwd=dashboard_dir)
    processes.append(p_dash)

    print("\n" + "*" * 70)
    print("  TRAFFICGUARD PLATFORM IS FULLY OPERATIONAL!")
    print("  - Gateway API:   http://127.0.0.1:8000")
    print("  - Proxy Route:   http://127.0.0.1:8000/api/v1/proxy/api/data")
    print("  - Prometheus:    http://127.0.0.1:8000/metrics")
    print("  - React UI:      http://localhost:3000")
    print("  Press Ctrl+C to terminate.")
    print("*" * 70 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
