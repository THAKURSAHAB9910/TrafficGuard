from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["Proxy Traffic Entrypoint"])


@router.api_route("/api/v1/proxy/{subpath:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@router.api_route("/proxy/{subpath:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_traffic(request: Request, subpath: str) -> Response:
    """Primary entry point for client requests routed through TrafficGuard."""
    proxy_engine = request.app.state.proxy_engine
    return await proxy_engine.forward(request, subpath)
