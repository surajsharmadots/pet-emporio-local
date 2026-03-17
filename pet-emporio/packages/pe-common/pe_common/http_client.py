import httpx
from typing import Any, Optional
from .exceptions import AppException
from .logging import get_logger

logger = get_logger(__name__)


class ServiceClient:
    def __init__(self, base_url: str, timeout: float = 10.0, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
        self._failures = 0
        self._open = False

    async def get(self, path: str, **kwargs) -> Any:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, json: dict = None, **kwargs) -> Any:
        return await self._request("POST", path, json=json, **kwargs)

    async def patch(self, path: str, json: dict = None, **kwargs) -> Any:
        return await self._request("PATCH", path, json=json, **kwargs)

    async def delete(self, path: str, **kwargs) -> Any:
        return await self._request("DELETE", path, **kwargs)

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        if self._open:
            raise AppException("CIRCUIT_OPEN", "Service temporarily unavailable", 503)
        for attempt in range(self.max_retries):
            try:
                response = await self._client.request(method, path, **kwargs)
                self._failures = 0
                if self._open:
                    self._open = False
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise AppException("UPSTREAM_ERROR", str(e), e.response.status_code)
            except Exception as e:
                self._failures += 1
                if self._failures >= 5:
                    self._open = True
                    logger.error("circuit_opened", service=self.base_url)
                if attempt == self.max_retries - 1:
                    raise AppException("SERVICE_UNAVAILABLE", f"Failed after {self.max_retries} attempts", 503)