import ipaddress
import secrets
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.core.config import settings
from app.schemas.system_control import LocalShutdownResponse
from app.services.local_app_control import (
    create_local_shutdown_request,
    is_local_app_control_ready,
)

router = APIRouter(prefix="/system")


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@router.post(
    "/shutdown",
    response_model=LocalShutdownResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_local_shutdown(
    request: Request,
    control_token: Annotated[str | None, Header(alias="X-Local-Control-Token")] = None,
) -> LocalShutdownResponse:
    if not is_local_app_control_ready():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="本地关闭功能未启用。")

    client_host = request.client.host if request.client else None
    if not _is_loopback_host(client_host):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅允许本机关闭服务。")

    origin = request.headers.get("origin")
    if origin and not _is_loopback_host(urlsplit(origin).hostname):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请求来源不是本机。")

    expected_token = settings.local_control_token or ""
    if not control_token or not secrets.compare_digest(control_token, expected_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="本地控制令牌无效。")

    create_local_shutdown_request()
    return LocalShutdownResponse(
        status="accepted",
        message="关闭请求已接收，前后端服务即将停止。",
    )
