import app.agent.controller as controller
from app.agent.state import store


class _StubAgent:
    def decide(self, message, state, neighborhoods=None, correlation_id=None):
        return (
            {
                "intent": state.intent,
                "criteria": {},
                "extracted_updates": {},
                "handoff": {"should": False, "reason": ""},
                "plan": {"action": "ASK", "message": "", "question_key": None, "filters": {}},
            },
            False,
        )


def test_triage_only_completion_returns_summary():
    session_id = "test_triage_completion"
    store.reset(session_id)
    state = store.get(session_id)

    state.intent = "comprar"
    state.set_triage_field("city", "Joao Pessoa")
    state.set_triage_field("neighborhood", "Manaira")
    state.set_triage_field("micro_location", "beira-mar")
    state.set_triage_field("property_type", "apartamento")
    state.set_triage_field("bedrooms", 4)
    state.set_triage_field("parking", 2)
    state.set_triage_field("budget", 1_000_000)
    state.set_triage_field("timeline", "30d")

    controller.TRIAGE_ONLY = True
    controller.get_agent = lambda: _StubAgent()

    result = controller.handle_message(session_id=session_id, message="ok")
    assert "Resumo da triagem" in result.get("reply", "")
    assert result.get("summary"), "Deve retornar payload de summary no fim da triagem"

