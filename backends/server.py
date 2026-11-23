import os
import sys
import time
import random
import asyncio
from typing import Optional
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

SERVICE_ID = os.getenv("SERVICE_ID", "backend-1")
SERVICE_NAME = os.getenv("SERVICE_NAME", f"Backend Node {SERVICE_ID}")
PORT = int(os.getenv("PORT", "8001"))

app = FastAPI(title=f"TrafficGuard Real Backend - {SERVICE_NAME}", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simulation control state
state = {
    "status": "UP",                # "UP" or "DOWN"
    "simulated_delay_ms": 0,      # Additional artificial latency in ms
    "simulated_error_rate": 0.0,  # 0.0 to 1.0 probability of returning 500
    "started_at": time.time(),
    "total_requests": 0,
    "active_connections": 0,
}


@app.middleware("http")
async def track_and_simulate(request: Request, call_next):
    # Pass through simulation controls and health check without delay/error
    path = request.url.path
    if path.startswith("/simulate") or path == "/health" or path == "/status":
        return await call_next(request)

    # If backend is simulated DOWN
    if state["status"] != "UP":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "Service Unavailable",
                "service_id": SERVICE_ID,
                "message": "Backend service is currently down (simulated failure).",
            },
        )

    state["total_requests"] += 1
    state["active_connections"] += 1

    try:
        # Simulate delay if configured
        delay = state["simulated_delay_ms"]
        if delay > 0:
            await asyncio.sleep(delay / 1000.0)

        # Simulate error if configured
        error_rate = state["simulated_error_rate"]
        if error_rate > 0.0 and random.random() < error_rate:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal Server Error",
                    "service_id": SERVICE_ID,
                    "message": f"Simulated failure injected (error rate: {error_rate*100:.1f}%)",
                },
            )

        response = await call_next(request)
        response.headers["X-Backend-Service"] = SERVICE_ID
        return response
    finally:
        state["active_connections"] = max(0, state["active_connections"] - 1)


@app.get("/health")
async def health_check():
    """Health check endpoint for active gateway monitoring."""
    if state["status"] != "UP":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{SERVICE_ID} is DOWN",
        )
    return {
        "status": "UP",
        "service_id": SERVICE_ID,
        "service_name": SERVICE_NAME,
        "uptime_seconds": round(time.time() - state["started_at"], 1),
        "simulated_delay_ms": state["simulated_delay_ms"],
        "simulated_error_rate": state["simulated_error_rate"],
        "active_connections": state["active_connections"],
    }


@app.get("/status")
async def get_status():
    """Detailed operational status."""
    return {
        "service_id": SERVICE_ID,
        "service_name": SERVICE_NAME,
        "port": PORT,
        "status": state["status"],
        "simulated_delay_ms": state["simulated_delay_ms"],
        "simulated_error_rate": state["simulated_error_rate"],
        "total_requests": state["total_requests"],
        "active_connections": state["active_connections"],
        "uptime_seconds": round(time.time() - state["started_at"], 1),
    }


@app.post("/simulate/delay")
async def set_delay(ms: int = 0):
    """Inject artificial latency in milliseconds."""
    state["simulated_delay_ms"] = max(0, ms)
    return {"message": f"Simulated delay set to {state['simulated_delay_ms']}ms", "service_id": SERVICE_ID}


@app.post("/simulate/error")
async def set_error(rate: float = 0.0):
    """Inject artificial error probability between 0.0 and 1.0."""
    state["simulated_error_rate"] = max(0.0, min(1.0, rate))
    return {
        "message": f"Simulated error rate set to {state['simulated_error_rate']*100:.1f}%",
        "service_id": SERVICE_ID,
    }


@app.post("/simulate/status")
async def set_status(status_str: str = "UP"):
    """Inject full service outage (DOWN) or restore (UP)."""
    state["status"] = "UP" if status_str.upper() == "UP" else "DOWN"
    return {"message": f"Service status set to {state['status']}", "service_id": SERVICE_ID}


@app.post("/simulate/reset")
async def reset_simulation():
    """Reset all fault injections back to clean baseline."""
    state["status"] = "UP"
    state["simulated_delay_ms"] = 0
    state["simulated_error_rate"] = 0.0
    return {"message": "Simulation settings reset to normal", "service_id": SERVICE_ID}


# Application workload endpoints
@app.get("/api/data")
async def get_sample_data(category: Optional[str] = "general"):
    """Cacheable sample data endpoint."""
    return {
        "service_id": SERVICE_ID,
        "timestamp": time.time(),
        "category": category,
        "items": [
            {"id": i, "name": f"Metric Record {i}", "value": round(random.uniform(10.0, 99.0), 2)}
            for i in range(1, 6)
        ],
    }


@app.get("/api/compute")
async def compute_workload(iterations: int = 10000):
    """Simulates CPU workload for testing concurrency limits and latency."""
    # Perform math calculations
    res = 0.0
    for i in range(1, min(iterations, 200000)):
        res += (i * 0.5) ** 0.5
    return {
        "service_id": SERVICE_ID,
        "computed_result": round(res, 2),
        "iterations": iterations,
        "active_connections": state["active_connections"],
    }


@app.api_route("/api/echo", methods=["GET", "POST", "PUT", "DELETE"])
async def echo_request(request: Request):
    """Echoes incoming request headers, query parameters, and body."""
    body = await request.body()
    return {
        "service_id": SERVICE_ID,
        "method": request.method,
        "url": str(request.url),
        "headers": dict(request.headers),
        "body_length": len(body),
        "timestamp": time.time(),
    }


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f"Starting {SERVICE_NAME} on port {port_arg}...")
    uvicorn.run(app, host="0.0.0.0", port=port_arg, log_level="info")
