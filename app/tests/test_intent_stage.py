from agent.state import SessionState
from agent import rules
from agent.controller import _short_reply_updates
from agent.presenter import build_summary_payload
from agent.scoring import compute_lead_score


def _state_with_basics(session_id: str = "s-basic") -> SessionState:
    s = SessionState(session_id)
    s.intent = "comprar"
    s.set_criterion("city", "Joao Pessoa")
    s.set_criterion("neighborhood", "Manaira")
    s.set_criterion("property_type", "apartamento")
    s.set_criterion("bedrooms", 3)
    s.set_criterion("budget", 800000)
    return s


def test_intent_stage_question_triggers_after_basics():
    state = _state_with_basics("s-gate")
    key = rules.next_best_question_key(state)
    assert key == "intent_stage"


def test_intent_stage_updates_from_reply_researching():
    state = _state_with_basics("s-research")
    state.last_question_key = "intent_stage"
    updates = _short_reply_updates("só olhando / pesquisando ainda", state)
    assert updates["intent_stage"]["value"] == "researching"
    state.apply_updates(updates)
    assert state.intent_stage == "researching"


def test_intent_stage_scoring_ready_to_visit():
    state = _state_with_basics("s-ready")
    state.intent_stage = "ready_to_visit"
    score = compute_lead_score(state)
    assert "intent_stage_ready_to_visit" in score["reasons"]
    assert score["score"] >= 8


def test_microcopy_budget_single_question_and_stable():
    state = SessionState("s-microcopy")
    q1 = rules.choose_question("budget", state)
    q2 = rules.choose_question("budget", state)
    assert q1 == q2  # estabilidade por sessão
    assert q1.count("?") == 1


def test_handoff_final_contains_corretor_and_contact_phrase():
    state = _state_with_basics("s-summary")
    state.intent_stage = "ready_to_visit"
    ls = compute_lead_score(state)
    state.lead_score.temperature = ls["temperature"]
    state.lead_score.score = ls["score"]
    state.lead_score.reasons = ls["reasons"]
    summary = build_summary_payload(state, assigned_agent={"name": "Maria", "whatsapp": "+550000"})
    text = summary["text"].lower()
    assert "corretor" in text
    assert "entrar em contato" in text
    # garante bullets
    assert text.count("- ") >= 2
