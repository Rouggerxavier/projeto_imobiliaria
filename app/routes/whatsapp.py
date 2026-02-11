"""
WhatsApp Cloud API webhook router.
Handles verification (GET) and event reception (POST) with signature validation.
"""
import hmac
import hashlib
import logging
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_signature(payload: bytes, signature: str) -> bool:
    """
    Verify X-Hub-Signature-256 header from WhatsApp webhook.

    Args:
        payload: Raw request body (bytes)
        signature: X-Hub-Signature-256 header value (format: "sha256=<hex>")

    Returns:
        True if signature is valid, False otherwise
    """
    if not settings.WHATSAPP_APP_SECRET:
        logger.warning("WHATSAPP_APP_SECRET not configured - signature validation skipped")
        return True  # Allow in dev mode when secret is not set

    if not signature or not signature.startswith("sha256="):
        logger.warning("Invalid signature format: %s", signature[:20] if signature else "None")
        return False

    expected_signature = signature.split("sha256=")[-1]
    computed_hmac = hmac.new(
        settings.WHATSAPP_APP_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(computed_hmac, expected_signature)


@router.get("/webhook/whatsapp")
async def whatsapp_verify(
    request: Request,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    WhatsApp webhook verification endpoint (GET).

    WhatsApp sends a verification request when you configure the webhook URL.
    We must validate the verify_token and return the challenge.

    Query params:
        hub.mode: Should be "subscribe"
        hub.verify_token: Token to verify (must match WHATSAPP_VERIFY_TOKEN)
        hub.challenge: Challenge string to return if verification succeeds
    """
    logger.info(
        "WhatsApp verification request - mode=%s, token_match=%s",
        hub_mode,
        hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN if settings.WHATSAPP_VERIFY_TOKEN else "N/A",
    )

    if not settings.WHATSAPP_VERIFY_TOKEN:
        logger.error("WHATSAPP_VERIFY_TOKEN not configured - cannot verify webhook")
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: WHATSAPP_VERIFY_TOKEN not set. Please configure environment variables.",
        )

    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verification successful - returning challenge")
        return PlainTextResponse(content=hub_challenge, status_code=200)

    logger.warning(
        "Webhook verification failed - mode=%s, token_match=%s",
        hub_mode,
        hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN,
    )
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    WhatsApp webhook event receiver (POST).

    Receives events from WhatsApp Cloud API (messages, status updates, etc).
    Validates signature, logs event, and responds quickly with 200 OK.

    Security:
        - Validates X-Hub-Signature-256 if WHATSAPP_APP_SECRET is configured
        - Logs event metadata without exposing PII
        - Returns 200 immediately (async processing recommended for production)
    """
    # Read raw body for signature validation
    body_bytes = await request.body()

    # Validate signature if APP_SECRET is configured
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body_bytes, signature):
        logger.warning(
            "Invalid webhook signature - rejecting request from %s",
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("Failed to parse webhook JSON: %s", str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Extract metadata for logging (avoid logging PII)
    event_type = payload.get("object", "unknown")
    entry_count = len(payload.get("entry", []))

    # Log event metadata safely
    event_ids = []
    message_count = 0
    for entry in payload.get("entry", []):
        entry_id = entry.get("id")
        if entry_id:
            event_ids.append(entry_id)
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            message_count += len(messages)

    logger.info(
        "WhatsApp webhook received - type=%s, entries=%d, event_ids=%s, messages=%d",
        event_type,
        entry_count,
        event_ids[:3],  # Log first 3 IDs only
        message_count,
    )

    # Log full payload in debug mode (sanitized by logging formatter)
    if settings.LOG_LEVEL.upper() == "DEBUG":
        logger.debug("Webhook payload: %s", payload)

    # TODO: Add async processing here
    # - Parse message content
    # - Call agent controller
    # - Queue response for sending
    # For now, just acknowledge receipt

    if settings.DISABLE_WHATSAPP_SEND:
        logger.info("Test mode active - webhook accepted but not processing (DISABLE_WHATSAPP_SEND=true)")

    # Respond quickly to avoid timeout
    return JSONResponse(content={"ok": True}, status_code=200)
