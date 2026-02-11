"""
WhatsApp Cloud API - Message Sender Service.
Handles sending text messages via WhatsApp Business API.
"""
import logging
import httpx
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# WhatsApp Cloud API version
WHATSAPP_API_VERSION = "v21.0"


class WhatsAppSendError(Exception):
    """Exception raised when WhatsApp message sending fails."""
    pass


async def send_whatsapp_message(to: str, message: str) -> dict:
    """
    Send a text message via WhatsApp Cloud API.

    Args:
        to: Phone number in international format (e.g., "5511999999999")
        message: Text message to send

    Returns:
        dict: Response from WhatsApp API containing message ID

    Raises:
        WhatsAppSendError: If sending fails or credentials are missing
    """
    # Check if sending is disabled
    if settings.DISABLE_WHATSAPP_SEND:
        logger.info(
            "WhatsApp send disabled - would send to %s: %s",
            to[:5] + "***" + to[-4:] if len(to) > 9 else to,
            message[:50] + "..." if len(message) > 50 else message,
        )
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": to, "wa_id": to}],
            "messages": [{"id": "test_message_id_" + to}],
        }

    # Validate credentials
    if not settings.WHATSAPP_ACCESS_TOKEN:
        logger.error("Cannot send message - WHATSAPP_ACCESS_TOKEN not configured")
        raise WhatsAppSendError("WHATSAPP_ACCESS_TOKEN not configured")

    if not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.error("Cannot send message - WHATSAPP_PHONE_NUMBER_ID not configured")
        raise WhatsAppSendError("WHATSAPP_PHONE_NUMBER_ID not configured")

    # Build API URL
    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    # Build request payload
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }

    # Build headers
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            # Log response (sanitize token from logs automatically via logging formatter)
            logger.info(
                "WhatsApp send attempt - to=%s, status=%d",
                to[:5] + "***" + to[-4:] if len(to) > 9 else to,
                response.status_code,
            )

            # Check for errors
            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                logger.error(
                    "WhatsApp send failed - status=%d, error=%s",
                    response.status_code,
                    error_data.get("error", {}).get("message", "Unknown error"),
                )
                raise WhatsAppSendError(
                    f"WhatsApp API returned {response.status_code}: {error_data}"
                )

            # Parse response
            result = response.json()
            message_id = result.get("messages", [{}])[0].get("id", "unknown")

            logger.info(
                "WhatsApp message sent successfully - message_id=%s, to=%s",
                message_id,
                to[:5] + "***" + to[-4:] if len(to) > 9 else to,
            )

            return result

    except httpx.TimeoutException as e:
        logger.error("WhatsApp send timeout - to=%s", to[:5] + "***" + to[-4:])
        raise WhatsAppSendError(f"Request timeout: {str(e)}")
    except httpx.RequestError as e:
        logger.error("WhatsApp send request error - to=%s, error=%s", to[:5] + "***" + to[-4:], str(e))
        raise WhatsAppSendError(f"Request error: {str(e)}")
    except Exception as e:
        logger.error("WhatsApp send unexpected error - to=%s, error=%s", to[:5] + "***" + to[-4:], str(e))
        raise WhatsAppSendError(f"Unexpected error: {str(e)}")


def extract_message_from_webhook(payload: dict) -> Optional[dict]:
    """
    Extract message data from WhatsApp webhook payload.

    Args:
        payload: Webhook payload from WhatsApp

    Returns:
        dict with keys: 'from', 'message_id', 'text', 'timestamp'
        None if no valid message found

    Example payload structure:
        {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "...",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {...},
                        "contacts": [...],
                        "messages": [{
                            "from": "5511999999999",
                            "id": "wamid.xxx",
                            "timestamp": "1234567890",
                            "text": {"body": "Hello"},
                            "type": "text"
                        }]
                    }
                }]
            }]
        }
    """
    try:
        entries = payload.get("entry", [])
        if not entries:
            return None

        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])

                for msg in messages:
                    # Only process text messages
                    if msg.get("type") != "text":
                        logger.debug("Skipping non-text message type: %s", msg.get("type"))
                        continue

                    # Extract data
                    from_number = msg.get("from")
                    message_id = msg.get("id")
                    text_body = msg.get("text", {}).get("body", "")
                    timestamp = msg.get("timestamp")

                    if from_number and text_body:
                        return {
                            "from": from_number,
                            "message_id": message_id,
                            "text": text_body,
                            "timestamp": timestamp,
                        }

        return None

    except Exception as e:
        logger.error("Error extracting message from webhook: %s", str(e))
        return None
