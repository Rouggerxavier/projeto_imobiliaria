"""
Configuration module for production environment.
All settings loaded via environment variables with secure defaults.
"""
import os
from typing import Literal


class Settings:
    """Application settings loaded from environment variables."""

    # Environment
    APP_ENV: Literal["production", "development"] = os.getenv("APP_ENV", "production")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # WhatsApp Cloud API
    WHATSAPP_VERIFY_TOKEN: str | None = os.getenv("WHATSAPP_VERIFY_TOKEN")
    WHATSAPP_APP_SECRET: str | None = os.getenv("WHATSAPP_APP_SECRET")
    WHATSAPP_ACCESS_TOKEN: str | None = os.getenv("WHATSAPP_ACCESS_TOKEN")
    WHATSAPP_PHONE_NUMBER_ID: str | None = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

    # Feature flags
    DISABLE_WHATSAPP_SEND: bool = os.getenv("DISABLE_WHATSAPP_SEND", "true").lower() == "true"

    # Server
    PORT: int = int(os.getenv("PORT", "8000"))

    # Security: API key for the generic /webhook endpoint
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    WEBHOOK_API_KEY: str | None = os.getenv("WEBHOOK_API_KEY")

    @classmethod
    def validate_whatsapp_config(cls) -> dict[str, str]:
        """Validate WhatsApp configuration and return warnings/errors."""
        issues = {"errors": [], "warnings": []}

        if not cls.WHATSAPP_VERIFY_TOKEN:
            issues["errors"].append("WHATSAPP_VERIFY_TOKEN is required for webhook verification")

        if not cls.WHATSAPP_APP_SECRET:
            issues["warnings"].append(
                "WHATSAPP_APP_SECRET not set - webhook signature validation disabled (not recommended for production)"
            )

        if cls.DISABLE_WHATSAPP_SEND:
            issues["warnings"].append("DISABLE_WHATSAPP_SEND=true - message sending is disabled (test mode)")

        if not cls.WHATSAPP_ACCESS_TOKEN and not cls.DISABLE_WHATSAPP_SEND:
            issues["warnings"].append("WHATSAPP_ACCESS_TOKEN not set - cannot send messages")

        if not cls.WEBHOOK_API_KEY:
            issues["warnings"].append(
                "WEBHOOK_API_KEY not set - /webhook endpoint is unprotected. "
                "Set it with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

        return issues


settings = Settings()
