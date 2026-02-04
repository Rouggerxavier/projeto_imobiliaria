import time
from agent.state import SessionState


def test_budget_single_value_no_conflict():
    state = SessionState("budget_single")
    state.set_current_turn(1)
    conflicts, _ = state.apply_updates({"budget": {"value": 1_500_000, "status": "confirmed", "source": "user", "raw_text": "1.5 mi"}})
    assert conflicts == []


def test_budget_conflict_with_evidence():
    state = SessionState("budget_conflict")
    state.set_current_turn(1)
    state.apply_updates({"budget": {"value": 1_000_000, "status": "confirmed", "source": "user", "raw_text": "1 mi"}})

    state.set_current_turn(3)
    conflicts, vals = state.apply_updates({"budget": {"value": 1_500_000, "status": "confirmed", "source": "user", "raw_text": "1.5 mi"}})
    assert conflicts == ["budget"]
    assert vals["budget"]["previous_turn_id"] == 1
    assert vals["budget"]["new_turn_id"] == 3


def test_session_reset_after_completed_greeting():
    state = SessionState("budget_reset")
    state.set_current_turn(1)
    state.apply_updates({"budget": {"value": 800_000, "status": "confirmed", "source": "user", "raw_text": "800k"}})
    state.completed = True
    state.last_activity_at = time.time() - 4000  # stale
    # Simula reset heurístico
    from agent.controller import _should_reset_session
    assert _should_reset_session(state, "Bom dia! Quero comprar em Manaira")
