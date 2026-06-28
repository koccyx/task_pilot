"""
Health check module for the Telegram Chat Logger Bot.

Provides a FastAPI web server with health check endpoints for container orchestration.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)


class HealthCheckServer:
    """FastAPI server for health check endpoints."""

    def __init__(self, port: int = 8080, host: str = "0.0.0.0"):
        """
        Initialize the health check server.

        Args:
            port: Port to run the server on (default: 8080)
            host: Host to bind to (default: 0.0.0.0)
        """
        self.port = port
        self.host = host
        self.app = self._create_app()
        self.server: uvicorn.Server | None = None

    def _create_app(self) -> FastAPI:
        """Create and configure the FastAPI application."""

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            """Application lifespan manager."""
            logger.info("Health check server starting...")
            yield
            logger.info("Health check server shutting down...")

        app = FastAPI(
            title="Telegram Chat Logger Bot Health Check",
            description="Health check endpoints for the Telegram Chat Logger Bot",
            version="1.0.0",
            lifespan=lifespan,
        )

        @app.get("/health")
        async def health_check() -> Dict[str, Any]:
            """Basic health check endpoint."""
            return {
                "status": "healthy",
                "service": "telegram-chat-logger-bot",
                "version": "1.0.0",
            }

        @app.get("/health/ready")
        async def readiness_check() -> Dict[str, Any]:
            """Readiness check endpoint for Kubernetes."""
            try:
                # Add any readiness checks here (database connections, etc.)
                return {
                    "status": "ready",
                    "service": "telegram-chat-logger-bot",
                    "checks": {
                        "bot_initialized": True,
                    },
                }
            except Exception as e:
                logger.error(f"Readiness check failed: {e}")
                raise HTTPException(status_code=503, detail="Service not ready")

        @app.get("/health/live")
        async def liveness_check() -> Dict[str, Any]:
            """Liveness check endpoint for Kubernetes."""
            return {
                "status": "alive",
                "service": "telegram-chat-logger-bot",
            }

        @app.get("/metrics", response_class=PlainTextResponse)
        async def metrics() -> PlainTextResponse:
            """Prometheus-compatible application metrics."""
            from .metrics import render_prometheus_metrics

            return PlainTextResponse(
                render_prometheus_metrics(),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )

        @app.get("/")
        async def root() -> Dict[str, Any]:
            """Root endpoint with service information."""
            return {
                "service": "Telegram Chat Logger Bot",
                "version": "1.0.0",
                "endpoints": {
                    "health": "/health",
                    "readiness": "/health/ready",
                    "liveness": "/health/live",
                    "metrics": "/metrics",
                },
            }

        return app

    async def start(self) -> None:
        """Start the health check server."""
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=True,
        )
        self.server = uvicorn.Server(config)

        # Run the server in a separate task
        asyncio.create_task(self.server.serve())
        logger.info(f"Health check server started on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the health check server."""
        if self.server:
            self.server.should_exit = True
            logger.info("Health check server stopped")
