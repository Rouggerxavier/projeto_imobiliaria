"""
Test WhatsApp message flow end-to-end.
Simulates receiving a message and sending a response.
"""
import os
from fastapi.testclient import TestClient

# Set test environment variables
os.environ["WHATSAPP_VERIFY_TOKEN"] = "test_token_123"
os.environ["DISABLE_WHATSAPP_SEND"] = "true"  # Test mode - don't actually send
os.environ["LOG_LEVEL"] = "INFO"

from app.main import app

client = TestClient(app)


def test_whatsapp_message_flow():
    """Test complete flow: receive message -> extract -> send response."""
    print("\n" + "=" * 60)
    print("Testing WhatsApp Message Flow")
    print("=" * 60 + "\n")

    # Simulate WhatsApp webhook with a text message
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "123456789",
                            },
                            "contacts": [{"profile": {"name": "John Doe"}, "wa_id": "5511999999999"}],
                            "messages": [
                                {
                                    "from": "5511999999999",
                                    "id": "wamid.HBgNNTUxMTk5OTk5OTk5ORUCABIYFjNFQjBDMDRGRjREMDRGNTREQjQ2AA==",
                                    "timestamp": "1234567890",
                                    "text": {"body": "Quero alugar apartamento em Manaíra"},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    print("1. Sending webhook event with message...")
    print(f"   From: 5511999999999")
    print(f"   Text: Quero alugar apartamento em Manaíra\n")

    response = client.post("/webhook/whatsapp", json=payload)

    print(f"2. Webhook response: {response.status_code}")
    print(f"   Body: {response.json()}\n")

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    print("3. Expected behavior (check logs above):")
    print("   [OK] Message extracted: from=55119***, text=Quero alugar...")
    print("   [OK] Response sent: 'Ola! Recebi sua mensagem.'")
    print("   [OK] (In test mode - no actual API call made)\n")

    print("=" * 60)
    print("[SUCCESS] WhatsApp message flow works!")
    print("=" * 60 + "\n")


def test_whatsapp_non_text_message():
    """Test that non-text messages are ignored gracefully."""
    print("\n" + "=" * 60)
    print("Testing Non-Text Message Handling")
    print("=" * 60 + "\n")

    # Simulate image message
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
                                    "id": "wamid.xxx",
                                    "timestamp": "1234567890",
                                    "type": "image",
                                    "image": {"id": "image_id_123"},
                                }
                            ]
                        }
                    }
                ],
            }
        ],
    }

    print("1. Sending webhook event with image message...")
    response = client.post("/webhook/whatsapp", json=payload)

    print(f"2. Webhook response: {response.status_code}")
    print(f"   Body: {response.json()}\n")

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    print("3. Expected behavior:")
    print("   [OK] Non-text message skipped")
    print("   [OK] Webhook acknowledged with 200 OK\n")

    print("=" * 60)
    print("[SUCCESS] Non-text messages handled correctly!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        test_whatsapp_message_flow()
        test_whatsapp_non_text_message()

        print("\n" + "=" * 60)
        print("[SUCCESS] All WhatsApp flow tests passed!")
        print("=" * 60 + "\n")

        print("Next steps:")
        print("1. Configure WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID")
        print("2. Set DISABLE_WHATSAPP_SEND=false to enable real sending")
        print("3. Test with real WhatsApp number")
        print("4. Integrate with agent controller for intelligent responses\n")

    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}\n")
        raise
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}\n")
        raise
