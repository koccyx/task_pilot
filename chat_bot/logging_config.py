"""Structured logging configuration for console output.

This module provides structured JSON logging to stdout (console).
"""

import json
import logging
import os
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, cast

# Try to import JSON logger
try:
    from pythonjsonlogger import jsonlogger
except ImportError:
    jsonlogger = None

F = TypeVar("F", bound=Callable[..., Any])

# Global logger instance
_structured_logger: Optional[logging.Logger] = None

_STANDARD_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


def _extract_extra_fields(record: logging.LogRecord) -> Dict[str, Any]:
    """Extract non-standard LogRecord fields for structured logging."""
    extra_fields: Dict[str, Any] = {}

    for key, value in record.__dict__.items():
        if key in _STANDARD_LOG_RECORD_FIELDS or key.startswith("_"):
            continue
        extra_fields[key] = sanitize_for_logging(value, max_length=2000)

    return extra_fields


# Define StructuredFormatter only if jsonlogger is available
if jsonlogger is not None:

    class StructuredFormatter(jsonlogger.JsonFormatter):
        """JSON formatter for structured logging."""

        def add_fields(
            self,
            log_record: Dict[str, Any],
            record: logging.LogRecord,
            message_dict: Dict[str, Any],
        ) -> None:
            """Add structured fields to log record.

            Args:
                log_record: Dictionary to populate with log data.
                record: Python logging record.
                message_dict: Parsed message dictionary.
            """
            super().add_fields(log_record, record, message_dict)

            # Add standard fields
            from datetime import timezone
            log_record["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            log_record["level"] = record.levelname
            log_record["logger"] = record.name
            log_record["message"] = record.getMessage()

            # Add context fields if available
            if hasattr(record, "method_name"):
                log_record["method_name"] = record.method_name
            if hasattr(record, "input_params"):
                log_record["input_params"] = record.input_params
            if hasattr(record, "result"):
                log_record["result"] = record.result
            if hasattr(record, "duration_ms"):
                log_record["duration_ms"] = record.duration_ms
            if hasattr(record, "error_type"):
                log_record["error_type"] = record.error_type
            if hasattr(record, "error_message"):
                log_record["error_message"] = record.error_message
            if hasattr(record, "traceback"):
                log_record["traceback"] = record.traceback

            # Add service identification
            log_record["service"] = "task_pilot-mcp-server"
            log_record["component"] = record.name.split(".")[0] if "." in record.name else record.name
            log_record.update(_extract_extra_fields(record))

else:
    # Fallback: StructuredFormatter is just an alias for SimpleJSONFormatter
    StructuredFormatter = None  # type: ignore


class SimpleJSONFormatter(logging.Formatter):
    """Simple JSON formatter when pythonjsonlogger is not available."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Logging record.

        Returns:
            JSON-formatted log string.
        """
        from datetime import timezone
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "task_pilot-mcp-server",
            "component": record.name.split(".")[0] if "." in record.name else record.name,
        }

        # Add extra fields
        if hasattr(record, "method_name"):
            log_data["method_name"] = record.method_name
        if hasattr(record, "input_params"):
            log_data["input_params"] = record.input_params
        if hasattr(record, "result"):
            log_data["result"] = record.result
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "error_type"):
            log_data["error_type"] = record.error_type
        if hasattr(record, "error_message"):
            log_data["error_message"] = record.error_message
        if hasattr(record, "traceback"):
            log_data["traceback"] = record.traceback

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        log_data.update(_extract_extra_fields(record))

        return json.dumps(log_data, ensure_ascii=False, default=str)


def setup_structured_logging(
    level: str = "INFO",
    use_json: bool = True,
) -> logging.Logger:
    """Setup structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        use_json: Whether to use JSON formatting.

    Returns:
        Configured logger instance.
    """
    global _structured_logger

    if _structured_logger is not None:
        return _structured_logger

    # Create root logger
    logger = logging.getLogger("chat_bot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    logger.handlers.clear()

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # Set formatter
    if use_json:
        if jsonlogger is not None and StructuredFormatter is not None:
            formatter = StructuredFormatter(
                "%(timestamp)s %(level)s %(logger)s %(message)s"
            )
        else:
            formatter = SimpleJSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _structured_logger = logger
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module.

    Args:
        name: Logger name (usually __name__).

    Returns:
        Logger instance.
    """
    if _structured_logger is None:
        # Auto-setup if not configured
        level = os.getenv("LOG_LEVEL", "INFO")
        use_json = os.getenv("LOG_JSON", "true").lower() == "true"
        setup_structured_logging(level=level, use_json=use_json)

    return logging.getLogger(name)


def sanitize_for_logging(data: Any, max_length: int = 1000) -> Any:
    """Sanitize data for logging (remove sensitive info, truncate long strings).

    Args:
        data: Data to sanitize.
        max_length: Maximum string length.

    Returns:
        Sanitized data.
    """
    if isinstance(data, str):
        # Truncate long strings
        if len(data) > max_length:
            return data[:max_length] + f"... (truncated, {len(data)} chars)"
        return data
    elif isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Skip sensitive fields
            if any(
                sensitive in key.lower()
                for sensitive in ["token", "password", "secret", "key", "auth"]
            ):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = sanitize_for_logging(value, max_length)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_for_logging(item, max_length) for item in data[:10]]  # Limit list size
    else:
        return data


def log_method_call(
    logger: Optional[logging.Logger] = None,
    log_input: bool = True,
    log_output: bool = True,
    log_errors: bool = True,
) -> Callable[[F], F]:
    """Decorator to log method calls with input parameters and results.

    Args:
        logger: Logger instance (if None, uses function's module logger).
        log_input: Whether to log input parameters.
        log_output: Whether to log output results.
        log_errors: Whether to log errors.

    Returns:
        Decorator function.
    """

    def decorator(func: F) -> F:
        func_logger = logger or get_logger(func.__module__)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Async wrapper for logging."""
            import time

            method_name = f"{func.__module__}.{func.__name__}"
            start_time = time.time()

            # Prepare input parameters
            input_params: Dict[str, Any] = {}
            if log_input:
                # Get function signature
                import inspect

                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()

                for param_name, param_value in bound_args.arguments.items():
                    # Skip context parameter
                    if param_name == "ctx":
                        continue
                    input_params[param_name] = sanitize_for_logging(param_value)

            # Log method entry
            func_logger.info(
                "Method called",
                extra={
                    "method_name": method_name,
                    "input_params": input_params,
                },
            )

            try:
                # Call the function
                result = await func(*args, **kwargs)

                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000

                # Prepare result for logging
                result_for_log: Any = None
                if log_output:
                    result_for_log = sanitize_for_logging(result, max_length=2000)

                # Log method completion
                func_logger.info(
                    "Method completed",
                    extra={
                        "method_name": method_name,
                        "result": result_for_log,
                        "duration_ms": round(duration_ms, 2),
                    },
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                if log_errors:
                    error_type = type(e).__name__
                    error_message = str(e)
                    error_traceback = traceback.format_exc()

                    func_logger.error(
                        "Method failed",
                        extra={
                            "method_name": method_name,
                            "error_type": error_type,
                            "error_message": error_message,
                            "traceback": error_traceback,
                            "duration_ms": round(duration_ms, 2),
                        },
                        exc_info=True,
                    )

                raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Sync wrapper for logging."""
            import time

            method_name = f"{func.__module__}.{func.__name__}"
            start_time = time.time()

            # Prepare input parameters
            input_params: Dict[str, Any] = {}
            if log_input:
                import inspect

                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()

                for param_name, param_value in bound_args.arguments.items():
                    if param_name == "ctx":
                        continue
                    input_params[param_name] = sanitize_for_logging(param_value)

            # Log method entry
            func_logger.info(
                "Method called",
                extra={
                    "method_name": method_name,
                    "input_params": input_params,
                },
            )

            try:
                # Call the function
                result = func(*args, **kwargs)

                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000

                # Prepare result for logging
                result_for_log: Any = None
                if log_output:
                    result_for_log = sanitize_for_logging(result, max_length=2000)

                # Log method completion
                func_logger.info(
                    "Method completed",
                    extra={
                        "method_name": method_name,
                        "result": result_for_log,
                        "duration_ms": round(duration_ms, 2),
                    },
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                if log_errors:
                    error_type = type(e).__name__
                    error_message = str(e)
                    error_traceback = traceback.format_exc()

                    func_logger.error(
                        "Method failed",
                        extra={
                            "method_name": method_name,
                            "error_type": error_type,
                            "error_message": error_message,
                            "traceback": error_traceback,
                            "duration_ms": round(duration_ms, 2),
                        },
                        exc_info=True,
                    )

                raise

        # Return appropriate wrapper based on function type
        import inspect

        if inspect.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        else:
            return cast(F, sync_wrapper)

    return decorator


@contextmanager
def log_intermediate_call(
    logger: logging.Logger,
    method_name: str,
    **params: Any,
):
    """Context manager for logging intermediate method calls.

    Args:
        logger: Logger instance.
        method_name: Name of the method being called.
        **params: Method parameters.

    Yields:
        None (for use in with statement).
    """
    import time

    start_time = time.time()
    sanitized_params = sanitize_for_logging(params)

    logger.debug(
        "Intermediate method call started",
        extra={
            "method_name": method_name,
            "input_params": sanitized_params,
        },
    )

    try:
        yield
        duration_ms = (time.time() - start_time) * 1000

        logger.debug(
            "Intermediate method call completed",
            extra={
                "method_name": method_name,
                "duration_ms": round(duration_ms, 2),
            },
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000

        logger.warning(
            "Intermediate method call failed",
            extra={
                "method_name": method_name,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "duration_ms": round(duration_ms, 2),
            },
        )
        raise
