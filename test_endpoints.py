"""
Quick test script for validating production endpoints.
Run this after deploying to ensure everything works.
"""
import os
from fastapi.testclient import TestClient

# Set test environment variables
os.environ["WHATSAPP_VERIFY_TOKEN"] = "test_token_123"
os.environ["DISABLE_WHATSAPP_SEND"] = "true"
os.environ["LOG_LEVEL"] = "WARNING"  # Suppress logs during test

from app.main import app

client = TestClient(app)


def test_home():
    """Test home page returns HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Agente Imobiliário API" in response.text
    print("[OK] GET / - Home page OK")


def test_health():
    """Test health check."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    print("[OK] GET /health - Health check OK")


def test_whatsapp_verification_success():
    """Test WhatsApp webhook verification (success)."""
    response = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_token_123",
            "hub.challenge": "challenge_12345",
        },
    )
    assert response.status_code == 200
    assert response.text == "challenge_12345"
    print("[OK] GET /webhook/whatsapp - Verification success OK")


def test_whatsapp_verification_fail():
    """Test WhatsApp webhook verification (fail - wrong token)."""
    response = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "challenge_12345",
        },
    )
    assert response.status_code == 403
    print("[OK] GET /webhook/whatsapp - Verification failure OK (403)")


def test_whatsapp_webhook_post():
    """Test WhatsApp webhook POST (event reception)."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "5511999999999",
                                    "id": "msg_123",
                                    "text": {"body": "Olá"},
                                }
                            ]
                        }
                    }
                ],
            }
        ],
    }
    response = client.post("/webhook/whatsapp", json=payload)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    print("[OK] POST /webhook/whatsapp - Event reception OK")


def test_existing_webhook():
    """Test existing agent webhook still works."""
    payload = {
        "session_id": "test-session",
        "message": "Quero alugar apartamento",
        "name": "Maria",
    }
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert "reply" in response.json()
    print("[OK] POST /webhook - Agent webhook OK")


def test_docs_available():
    """Test that Swagger docs are available."""
    response = client.get("/docs")
    assert response.status_code == 200
    print("[OK] GET /docs - Swagger UI OK")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Testing Production Endpoints")
    print("=" * 60 + "\n")

    try:
        test_home()
        test_health()
        test_whatsapp_verification_success()
        test_whatsapp_verification_fail()
        test_whatsapp_webhook_post()
        test_existing_webhook()
        test_docs_available()

        print("\n" + "=" * 60)
        print("[SUCCESS] All tests passed! Ready for production.")
        print("=" * 60 + "\n")

    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}\n")
        raise
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}\n")
        raise
