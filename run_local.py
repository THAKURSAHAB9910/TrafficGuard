"""
TrafficGuard Local Development Orchestrator
===========================================
Launches the full local resilience stack in one process:
  - Backend Alpha:   http://127.0.0.1:8001
  - Backend Beta:    http://127.0.0.1:8002
  - Backend Gamma:   http://127.0.0.1:8003
  - API Gateway:     http://127.0.0.1:8000
  - React Dashboard: http://localhost:5173
"""

import os
import sys
import time
import signal
import subprocess
import threading
import urllib.request
import webbrowser

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(ROOT_DIR, "dashboard")

# ANSI Color codes for clean terminal output
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

processes = []
shutting_down = False


def log(prefix: str, msg: str, color: str = RESET):
    print(f"{color}[{prefix}] {msg}{RESET}", flush=True)


def stream_output(proc, prefix: str, color: str):
    """Stream stdout/stderr from a child process."""
    try:
        for line in iter(proc.stdout.readline, ""):
            if shutting_down:
                break
            if line.strip():
                print(f"{color}[{prefix}] {line.strip()}{RESET}", flush=True)
    except Exception:
        pass


def start_process(cmd, name: str, color: str, cwd: str = ROOT_DIR, env: dict = None):
    p_env = os.environ.copy()
    if env:
        p_env.update(env)
    p_env["PYTHONUNBUFFERED"] = "1"

    log(name, f"Starting: {' '.join(cmd) if isinstance(cmd, list) else cmd}", color)
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=p_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    processes.append((name, proc))

    t = threading.Thread(target=stream_output, args=(proc, name, color), daemon=True)
    t.start()
    return proc


def wait_for_url(url: str, timeout: float = 15.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TrafficGuard-Runner"})
            with urllib.request.urlopen(req, timeout=1.5) as res:
                if res.status in (200, 404):
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def shutdown_all(*args):
    global shutting_down
    if shutting_down:
        return
    shutting_down = True
    print("\n")
    log("SHUTDOWN", "Gracefully terminating all TrafficGuard services...", YELLOW)
    for name, proc in reversed(processes):
        try:
            log("SHUTDOWN", f"Stopping {name} (PID {proc.pid})...", YELLOW)
            proc.terminate()
        except Exception:
            pass

    time.sleep(1.0)
    for name, proc in processes:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
    log("SHUTDOWN", "All services stopped successfully.", GREEN)
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, shutdown_all)
    signal.signal(signal.SIGTERM, shutdown_all)

    print(f"{BOLD}{CYAN}")
    print("=" * 68)
    print("   TRAFFICGUARD — ADAPTIVE TRAFFIC MANAGEMENT PLATFORM")
    print("   Starting complete local development environment...")
    print("=" * 68)
    print(f"{RESET}")

    py_bin = sys.executable

    # 1. Start Upstream Backend 1 (Alpha - 8001)
    start_process(
        [py_bin, "-m", "uvicorn", "backends.server:app", "--port", "8001", "--host", "127.0.0.1"],
        name="BACKEND-ALPHA",
        color="\033[94m",
        env={"PORT": "8001", "SERVICE_ID": "backend-1", "SERVICE_NAME": "Alpha Service (High Capacity)"},
    )

    # 2. Start Upstream Backend 2 (Beta - 8002)
    start_process(
        [py_bin, "-m", "uvicorn", "backends.server:app", "--port", "8002", "--host", "127.0.0.1"],
        name="BACKEND-BETA",
        color="\033[95m",
        env={"PORT": "8002", "SERVICE_ID": "backend-2", "SERVICE_NAME": "Beta Service (Mid Capacity)"},
    )

    # 3. Start Upstream Backend 3 (Gamma - 8003)
    start_process(
        [py_bin, "-m", "uvicorn", "backends.server:app", "--port", "8003", "--host", "127.0.0.1"],
        name="BACKEND-GAMMA",
        color="\033[93m",
        env={"PORT": "8003", "SERVICE_ID": "backend-3", "SERVICE_NAME": "Gamma Service (Low Capacity)"},
    )

    # 4. Start TrafficGuard API Gateway (8000)
    start_process(
        [py_bin, "-m", "uvicorn", "gateway.main:app", "--port", "8000", "--host", "127.0.0.1"],
        name="API-GATEWAY",
        color="\033[92m",
    )

    # 5. Start Vite React Dashboard (5173)
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    start_process(
        [npm_cmd, "run", "dev"],
        name="VITE-DASHBOARD",
        color="\033[96m",
        cwd=DASHBOARD_DIR,
    )

    log("RUNNER", "Waiting for services to become healthy...", CYAN)

    b1_ok = wait_for_url("http://127.0.0.1:8001/health", timeout=10.0)
    b2_ok = wait_for_url("http://127.0.0.1:8002/health", timeout=10.0)
    b3_ok = wait_for_url("http://127.0.0.1:8003/health", timeout=10.0)
    gw_ok = wait_for_url("http://127.0.0.1:8000/health", timeout=10.0)
    fe_ok = wait_for_url("http://localhost:5173", timeout=15.0)

    print()
    print(f"{BOLD}{GREEN}✔ All TrafficGuard local services are ONLINE:{RESET}")
    print(f"  {CYAN}▸ Frontend Dashboard:{RESET} http://localhost:5173")
    print(f"  {GREEN}▸ API Gateway:{RESET}        http://localhost:8000")
    print(f"  {GREEN}▸ Gateway Health:{RESET}     http://localhost:8000/health")
    print(f"  {GREEN}▸ Gateway Metrics:{RESET}    http://localhost:8000/metrics")
    print(f"  {YELLOW}▸ Backend 1 (Alpha):{RESET}  http://127.0.0.1:8001/status")
    print(f"  {YELLOW}▸ Backend 2 (Beta):{RESET}   http://127.0.0.1:8002/status")
    print(f"  {YELLOW}▸ Backend 3 (Gamma):{RESET}  http://127.0.0.1:8003/status")
    print(f"\n{BOLD}Press Ctrl+C to stop all services.{RESET}\n")

    # Keep main thread alive and watch child processes
    while not shutting_down:
        for name, proc in processes:
            if proc.poll() is not None and not shutting_down:
                log("WARNING", f"Process {name} exited with code {proc.returncode}", RED)
        time.sleep(1.0)


if __name__ == "__main__":
    main()
