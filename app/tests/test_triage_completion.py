"""
Regression test for triage completion without LLM calls.

This test ensures that when all critical fields are filled in TRIAGE_ONLY mode,
the system correctly generates a summary and completes without UnboundLocalError.
"""

import os
import sys
from unittest.mock import patch, MagicMock

# Setup path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_triage_completion_no_llm():
    """
    Test that triage completion works when all critical fields are pre-filled.
    This is a regression test for the UnboundLocalError bug where 'question'
    variable was referenced but not defined in the triage completion path.
    """
    # Enable TRIAGE_ONLY mode
    with patch.dict(os.environ, {"TRIAGE_ONLY": "true"}):
        # Force reload of modules to pick up env var
        import importlib
        from agent import controller, state, rules, llm

        importlib.reload(llm)
        importlib.reload(rules)
        importlib.reload(controller)

        # Create a fresh session
        session_id = "test_triage_complete_session"
        test_state = state.store.get(session_id)

        # Pre-fill all critical fields to simulate completed triage
        test_state.intent = "alugar"
        test_state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
        test_state.set_triage_field("neighborhood", "Tambaú", status="confirmed", source="user")
        test_state.set_triage_field("property_type", "apartamento", status="confirmed", source="user")
        test_state.set_triage_field("bedrooms", 2, status="confirmed", source="user")
        test_state.set_triage_field("parking", 1, status="confirmed", source="user")
        test_state.set_triage_field("budget", 3000, status="confirmed", source="user")
        test_state.set_triage_field("timeline", "3m", status="confirmed", source="user")
        test_state.set_triage_field("micro_location", "beira-mar", status="confirmed", source="user")

        # Mock the AI agent's decide method to return minimal decision without LLM call
        mock_decision = {
            "intent": None,  # Already set
            "criteria": {},
            "extracted_updates": {},
            "handoff": {"should": False},
            "plan": {"action": "ASK", "message": ""},
        }

        # Mock get_neighborhoods to avoid external dependencies
        with patch("agent.tools.get_neighborhoods", return_value=["Tambaú", "Cabo Branco", "Manaíra"]):
            # Mock the agent's decide method
            with patch("agent.controller.get_agent") as mock_get_agent:
                mock_agent = MagicMock()
                mock_agent.decide.return_value = (mock_decision, False)
                mock_get_agent.return_value = mock_agent

                # Call handle_message with a simple message
                result = controller.handle_message(
                    session_id=session_id,
                    message="Ok, está tudo certo",
                    name="Test User"
                )

        # Verify the response contains summary
        assert "reply" in result, "Response should contain 'reply' field"
        assert "state" in result, "Response should contain 'state' field"
        assert "summary" in result, "Response should contain 'summary' field for completed triage"
        assert "handoff" in result, "Response should contain 'handoff' field for completed triage"

        # Verify the reply contains the summary or SLA text (HOT/WARM/COLD)
        reply = result["reply"]
        assert ("Entendi o que você precisa" in reply or
                "corretor" in reply.lower() or
                "triagem" in reply.lower() or
                "acionei" in reply.lower() or
                "instantes" in reply.lower()), \
            f"Reply should contain summary text, got: {reply}"

        # Verify state was marked as completed
        final_state = result["state"]
        assert final_state["completed"] is True, "State should be marked as completed"

        # Verify summary payload has expected structure
        summary = result["summary"]
        assert "session_id" in summary, "Summary should contain session_id"
        assert "critical" in summary, "Summary should contain critical fields"
        assert "lead_score" in summary, "Summary should contain lead_score"
        assert summary["status"] == "triage_completed", "Summary status should be triage_completed"

        # Verify critical fields are populated
        critical = summary["critical"]
        assert critical["intent"] == "alugar", "Intent should be 'alugar'"
        assert critical["city"] == "Joao Pessoa", "City should be 'Joao Pessoa'"
        assert critical["neighborhood"] == "Tambaú", "Neighborhood should be 'Tambaú'"
        assert critical["property_type"] == "apartamento", "Property type should be 'apartamento'"
        assert critical["bedrooms"] == 2, "Bedrooms should be 2"
        assert critical["parking"] == 1, "Parking should be 1"
        assert critical["budget"] == 3000, "Budget should be 3000"
        assert critical["timeline"] == "3m", "Timeline should be '3m'"

        # Clean up
        state.store.reset(session_id)


def test_triage_with_greeting():
    """
    Test that greeting is properly prepended to summary when user sends a greeting.
    """
    # Enable TRIAGE_ONLY mode
    with patch.dict(os.environ, {"TRIAGE_ONLY": "true"}):
        import importlib
        from agent import controller, state, rules, llm

        importlib.reload(llm)
        importlib.reload(rules)
        importlib.reload(controller)

        session_id = "test_greeting_session"
        test_state = state.store.get(session_id)

        # Pre-fill all critical fields
        test_state.intent = "comprar"
        test_state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
        test_state.set_triage_field("neighborhood", "Cabo Branco", status="confirmed", source="user")
        test_state.set_triage_field("property_type", "casa", status="confirmed", source="user")
        test_state.set_triage_field("bedrooms", 3, status="confirmed", source="user")
        test_state.set_triage_field("parking", 2, status="confirmed", source="user")
        test_state.set_triage_field("budget", 500000, status="confirmed", source="user")
        test_state.set_triage_field("timeline", "6m", status="confirmed", source="user")
        test_state.set_triage_field("micro_location", "1_quadra", status="confirmed", source="user")

        mock_decision = {
            "intent": None,
            "criteria": {},
            "extracted_updates": {},
            "handoff": {"should": False},
            "plan": {"action": "ASK", "message": ""},
        }

        with patch("agent.tools.get_neighborhoods", return_value=["Tambaú", "Cabo Branco"]):
            with patch("agent.controller.get_agent") as mock_get_agent:
                mock_agent = MagicMock()
                mock_agent.decide.return_value = (mock_decision, False)
                mock_get_agent.return_value = mock_agent

                # Send message with greeting
                result = controller.handle_message(
                    session_id=session_id,
                    message="Bom dia! Tudo certo",
                    name="Test User"
                )

        reply = result["reply"]

        # Verify greeting was prepended
        assert reply.startswith("Bom dia!") or reply.startswith("Olá!"), \
            f"Reply should start with greeting, got: {reply}"

        # Verify summary or SLA message is still included after greeting
        assert ("Entendi o que você precisa" in reply or
                "corretor" in reply.lower() or
                "triagem" in reply.lower() or
                "acionei" in reply.lower() or
                "instantes" in reply.lower()), \
            "Reply should still contain summary after greeting"

        # Clean up
        state.store.reset(session_id)

        print(f"✓ Test passed: Greeting properly prepended to summary")
        print(f"✓ Reply: {reply}")


if __name__ == "__main__":
    test_triage_completion_no_llm()
    test_triage_with_greeting()
    print("\n✅ All tests passed!")
