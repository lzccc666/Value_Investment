from fastapi import HTTPException, status

from app.market_data.contracts import (
    MarketDataError,
    MarketDataNotConfiguredError,
    MarketDataRateLimitedError,
    MarketDataValidationError,
    UnsupportedMarketDataError,
)


def market_data_http_exception(exc: MarketDataError) -> HTTPException:
    status_code = status.HTTP_502_BAD_GATEWAY
    headers = None
    if isinstance(exc, (MarketDataValidationError, UnsupportedMarketDataError)):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, MarketDataNotConfiguredError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(exc, MarketDataRateLimitedError):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
        headers = {"Retry-After": "60"}
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
        headers=headers,
    )
