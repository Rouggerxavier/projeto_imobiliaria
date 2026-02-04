from agent.presenter import build_summary_payload
from agent.state import SessionState
from agent.scoring import compute_lead_score


def test_handoff_message_contains_summary_and_contact_phrase():
    state = SessionState("handoff1")
    state.intent = "comprar"
    state.set_criterion("city", "Joao Pessoa")
    state.set_criterion("neighborhood", "Manaira")
    state.set_criterion("property_type", "apartamento")
    state.set_criterion("bedrooms", 3)
    state.set_criterion("parking", 2)
    state.set_criterion("budget", 900000)
    state.set_criterion("timeline", "3m")
    ls = compute_lead_score(state)
    state.lead_score.temperature = ls["temperature"]
    state.lead_score.score = ls["score"]
    state.lead_score.reasons = ls["reasons"]

    summary = build_summary_payload(state, assigned_agent={"name": "Maria", "whatsapp": "+55000"})
    text = summary["text"].lower()
    assert "resumo da triagem" in text
    assert "corretor" in text
    assert "entrar em contato" in text
