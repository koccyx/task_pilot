"""Pure HTTP client for Kaiten API.

This module provides a thin HTTP client for making requests to Kaiten API.
All business logic (e.g., board resolution) should be in MCP tools, not here.

Includes singleton factory for efficient client reuse across MCP tools.
The singleton is automatically cleaned up at process exit via atexit.
"""

import atexit
import asyncio
import logging
import time
from typing import Any, Dict, Optional, cast

import httpx
from httpx import RequestError, Response

from chat_bot.logging_config import get_logger, log_method_call
from chat_bot.mcp_server.config.settings import Settings

logger = get_logger(__name__)

MAX_RATE_LIMIT_RETRIES = 3

# Module-level singleton instances for efficient reuse
_client_instance: Optional["KaitenClient"] = None
_settings_instance: Optional[Settings] = None


def _cleanup_at_exit() -> None:
    """Synchronous cleanup handler for atexit.

    Closes the KaitenClient singleton when the process exits.
    """
    global _client_instance
    if _client_instance is not None:
        logger.info("Cleaning up KaitenClient singleton at exit")
        try:
            # Try to get or create an event loop for cleanup
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(_client_instance.close())
        except Exception as e:
            logger.warning(f"Error during KaitenClient cleanup: {e}")
        finally:
            _client_instance = None


# Register cleanup handler
atexit.register(_cleanup_at_exit)


class KaitenClient:
    """Pure HTTP client for Kaiten API.

    This client handles only HTTP communication - no business logic.
    Use MCP tools for business logic like board name resolution.

    Attributes:
        base_url: Base URL for Kaiten API.
        token: Bearer token for authentication.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize Kaiten API client.

        Args:
            settings: Application settings with API URL and token.
        """
        self.base_url: str = settings.kaiten_api_url
        self.token: str = settings.kaiten_api_token
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    @log_method_call(log_input=True, log_output=False, log_errors=True)
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Response:
        """Make HTTP request to Kaiten API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            endpoint: API endpoint path.
            data: Optional request body data.

        Returns:
            Response object from httpx library.

        Raises:
            RequestError: If request fails.
        """
        url: str = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(
            "Making %s request to %s",
            method,
            url,
            extra={
                "method_name": "kaiten_client._request",
                "input_params": {
                    "method": method,
                    "endpoint": endpoint,
                    "url": url,
                    "has_data": data is not None,
                },
            },
        )

        try:
            for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
                response: Response = await self._client.request(
                    method=method,
                    url=url,
                    json=data,
                )
                if response.status_code != 429 or attempt == MAX_RATE_LIMIT_RETRIES:
                    break

                retry_after = response.headers.get("Retry-After")
                reset_at = response.headers.get("X-RateLimit-Reset")
                if retry_after:
                    delay = max(float(retry_after), 0.1)
                elif reset_at:
                    delay = max(float(reset_at) - time.time(), 0.1)
                else:
                    delay = 0.5 * (attempt + 1)
                logger.warning(
                    "Kaiten rate limit reached; retrying in %.2fs (attempt %d/%d)",
                    delay,
                    attempt + 1,
                    MAX_RATE_LIMIT_RETRIES,
                )
                await asyncio.sleep(delay)
            response.raise_for_status()

            # Log response summary (not full body to avoid huge logs)
            response_data: Any = None
            try:
                response_data = response.json()
                # Truncate large responses
                if isinstance(response_data, dict) and len(str(response_data)) > 500:
                    response_data = {"_truncated": True, "keys": list(response_data.keys())[:10]}
            except Exception:
                response_data = {"_type": "non_json", "status_code": response.status_code}

            logger.info(
                "Successfully completed %s request to %s",
                method,
                endpoint,
                extra={
                    "method_name": "kaiten_client._request",
                    "result": {
                        "status_code": response.status_code,
                        "response_preview": response_data,
                    },
                },
            )
            return response
        except RequestError as e:
            logger.error(
                "Request failed: %s %s - %s",
                method,
                url,
                str(e),
                extra={
                    "method_name": "kaiten_client._request",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True,
            )
            raise

    async def get(self, endpoint: str) -> Dict[str, Any]:
        """Make GET request to Kaiten API.

        Args:
            endpoint: API endpoint path.

        Returns:
            JSON response as dictionary.

        Raises:
            RequestError: If request fails.
        """
        response: Response = await self._request("GET", endpoint)
        return cast(Dict[str, Any], response.json())

    async def post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request to Kaiten API.

        Args:
            endpoint: API endpoint path.
            data: Request body data.

        Returns:
            JSON response as dictionary.

        Raises:
            RequestError: If request fails.
        """
        response: Response = await self._request("POST", endpoint, data)
        return cast(Dict[str, Any], response.json())

    async def put(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make PUT request to Kaiten API.

        Args:
            endpoint: API endpoint path.
            data: Request body data.

        Returns:
            JSON response as dictionary.

        Raises:
            RequestError: If request fails.
        """
        response: Response = await self._request("PUT", endpoint, data)
        return cast(Dict[str, Any], response.json())

    async def patch(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make PATCH request to Kaiten API.

        Args:
            endpoint: API endpoint path.
            data: Request body data.

        Returns:
            JSON response as dictionary.

        Raises:
            RequestError: If request fails.
        """
        response: Response = await self._request("PATCH", endpoint, data)
        return cast(Dict[str, Any], response.json())

    async def delete(self, endpoint: str) -> None:
        """Make DELETE request to Kaiten API.

        Args:
            endpoint: API endpoint path.

        Raises:
            RequestError: If request fails.
        """
        await self._request("DELETE", endpoint)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "KaitenClient":
        """Async context manager entry.

        Returns:
            Self for use in async with statement.
        """
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        """Async context manager exit.

        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.
        """
        await self.close()


def get_kaiten_client() -> KaitenClient:
    """Get or create shared KaitenClient instance.

    This factory function implements singleton pattern to avoid
    creating new HTTP clients on every tool call, saving ~50-100ms per call.

    Returns:
        Shared KaitenClient instance.

    Raises:
        ValueError: If required environment variables are missing.
    """
    global _client_instance, _settings_instance
    if _client_instance is None:
        logger.info("Creating shared KaitenClient instance")
        _settings_instance = Settings.from_env()
        _client_instance = KaitenClient(_settings_instance)
    return _client_instance


async def close_kaiten_client() -> None:
    """Close and cleanup the shared KaitenClient instance.

    Should be called during application shutdown to properly
    close HTTP connections.
    """
    global _client_instance
    if _client_instance is not None:
        logger.info("Closing shared KaitenClient instance")
        await _client_instance.close()
        _client_instance = None
