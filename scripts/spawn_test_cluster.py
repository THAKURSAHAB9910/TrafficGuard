import os
import sys
import subprocess
import time
import httpx

processes = []

try:
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
        p = subprocess.Popen(cmd, env=env)
        processes.append(p)

    time.sleep(1.0)
    p_gw = subprocess.Popen([sys.executable, "-m", "uvicorn", "gateway.main:app", "--port", "8000", "--host", "127.0.0.1", "--log-level", "warning"])
    processes.append(p_gw)

    # Retry health check until server is up
    healthy = False
    with httpx.Client(timeout=2.0) as client:
        for attempt in range(15):
            time.sleep(1.0)
            try:
                r = client.get("http://127.0.0.1:8000/health")
                if r.status_code == 200:
                    print("Gateway is UP and healthy:", r.json())
                    healthy = True
                    break
            except Exception:
                pass

    if not healthy:
        print("Failed to connect to gateway after 15s")
        sys.exit(1)

    print("All services running. Keeping cluster alive...")
    # Keep alive while child processes run
    p_gw.wait()

except KeyboardInterrupt:
    pass
finally:
    for p in processes:
        p.terminate()
