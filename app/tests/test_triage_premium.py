import json
from agent.state import SessionState
from agent import rules
from agent.extractor import extract_criteria
from agent.controller import _short_reply_updates
from agent.scoring import compute_lead_score
from agent.persistence import persist_state
import agent.persistence as persistence


def reset_state_filled():
    s = SessionState("s-test")
    s.intent = "alugar"
    s.set_criterion("city", "Joao Pessoa")
    s.set_criterion("neighborhood", "Manaíra")
    s.set_criterion("property_type", "apartamento")
    s.set_criterion("bedrooms", 3)
    s.set_criterion("suites", 1)
    s.set_criterion("parking", 2)
    s.set_criterion("budget", 5000)
    s.set_criterion("timeline", "3m")
    s.lead_profile["name"] = "Maria"
    return s


def test_micro_location_question_after_orla():
    state = reset_state_filled()
    state.apply_updates({"micro_location": {"value": "orla", "status": "inferred"}})
    missing = rules.missing_critical_fields(state)
    assert "micro_location" in missing
    qkey = rules.next_best_question_key(state)
    assert qkey == "micro_location"
    question = rules.choose_question(qkey, state)
    assert "quadra" in question


def test_budget_normalization_million():
    state = SessionState("s-budget")
    state.apply_updates({"budget": {"value": "1 milhão", "status": "confirmed", "source": "user"}})
    assert state.criteria.budget == 1_000_000


def test_timeline_inferred_fast():
    state = SessionState("s-time")
    state.apply_updates({"timeline": {"value": "o mais rápido possível", "status": "inferred"}})
    assert state.criteria.timeline == "3m"
    assert state.triage_fields["timeline"]["status"] == "inferred"


def test_leisure_multi_selection_list():
    extracted = extract_criteria("quero piscina, academia e playground", [])
    assert set(extracted.get("leisure_features", [])) >= {"piscina", "academia", "playground"}


def test_short_yes_updates_boolean():
    state = SessionState("s-yes")
    state.last_question_key = "pet"
    updates = _short_reply_updates("pode", state)
    assert updates["pet"]["value"] is True


def test_conflict_triggers_on_confirmed_field():
    state = SessionState("s-conflict")
    state.apply_updates({"budget": {"value": 5000, "status": "confirmed"}})
    conflicts, conflict_vals = state.apply_updates({"budget": {"value": 6000, "status": "confirmed"}})
    assert "budget" in conflicts
    assert conflict_vals["budget"]["previous"] == 5000


def test_lead_scoring_hot_warm_cold():
    hot = reset_state_filled()
    hot.set_criterion("timeline", "30d")
    assert compute_lead_score(hot)["temperature"] == "hot"

    warm = SessionState("s-warm")
    warm.intent = "comprar"
    warm.set_criterion("city", "Joao Pessoa")
    warm.set_criterion("budget", 700000)
    warm.set_criterion("timeline", "6m")
    assert compute_lead_score(warm)["temperature"] == "warm"

    cold = SessionState("s-cold")
    assert compute_lead_score(cold)["temperature"] == "cold"


def test_persist_state_writes_line(tmp_path):
    state = reset_state_filled()
    state.completed = True
    ls = compute_lead_score(state)
    state.lead_score.temperature = ls["temperature"]
    state.lead_score.score = ls["score"]
    state.lead_score.reasons = ls["reasons"]
    custom_path = tmp_path / "leads.jsonl"
    persistence.LEADS_PATH = str(custom_path)
    persist_state(state)
    with open(custom_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["session_id"] == state.session_id
    assert "lead_score" in obj
