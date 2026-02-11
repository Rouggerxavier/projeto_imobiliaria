"""
Structured logging configuration.
Sanitizes sensitive data (tokens, secrets) from logs.
"""
import logging
import sys
from typing import Any
from app.core.config import settings


class SanitizingFormatter(logging.Formatter):
    """Formatter that redacts sensitive information from log records."""

    SENSITIVE_KEYS = {
        "token",
        "secret",
        "password",
        "api_key",
        "access_token",
        "verify_token",
        "app_secret",
        "authorization",
        "x-hub-signature",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record and sanitize sensitive data."""
        # Sanitize message if it contains sensitive patterns
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self._sanitize_string(record.msg)

        # Sanitize args if present
        if record.args:
            sanitized_args = []
            for arg in record.args:
                if isinstance(arg, dict):
                    sanitized_args.append(self._sanitize_dict(arg))
                elif isinstance(arg, str):
                    sanitized_args.append(self._sanitize_string(arg))
                else:
                    sanitized_args.append(arg)
            record.args = tuple(sanitized_args)

        return super().format(record)

    def _sanitize_string(self, text: str) -> str:
        """Redact sensitive patterns in strings."""
        # Simple pattern matching for common token formats
        import re

        # Redact bearer tokens
        text = re.sub(r"Bearer\s+[\w\-\.]+", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
        # Redact API keys (common patterns)
        text = re.sub(r"['\"]?(?:token|key|secret)['\"]?\s*[:=]\s*['\"]?[\w\-]{16,}['\"]?", "[REDACTED]", text, flags=re.IGNORECASE)
        return text

    def _sanitize_dict(self, data: dict) -> dict:
        """Recursively sanitize dictionary values."""
        sanitized = {}
        for key, value in data.items():
            key_lower = key.lower().replace("-", "_").replace(" ", "_")
            if any(sensitive in key_lower for sensitive in self.SENSITIVE_KEYS):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_dict(value)
            elif isinstance(value, str):
                sanitized[key] = self._sanitize_string(value)
            else:
                sanitized[key] = value
        return sanitized


def setup_logging():
    """Configure structured logging for the application."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    # Create formatter
    formatter = SanitizingFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers = []
    root_logger.addHandler(handler)

    # Set specific loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    return logging.getLogger(__name__)


# Initialize logging
logger = setup_logging()
