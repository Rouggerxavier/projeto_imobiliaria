from agent.state import SessionState
from agent.rules import can_search_properties, missing_critical_fields


def test_can_search_properties_buy_missing_budget():
    state = SessionState(session_id="s1", intent="comprar")
    state.set_criterion("city", "João Pessoa")
    state.set_criterion("property_type", "apartamento")
    assert can_search_properties(state) is False


def test_can_search_properties_rent_ready():
    state = SessionState(session_id="s2", intent="alugar")
    state.set_criterion("city", "João Pessoa")
    state.set_criterion("property_type", "apartamento")
    state.set_criterion("budget", 3000)
    assert can_search_properties(state) is True


def test_missing_critical_fields_order():
    state = SessionState(session_id="s3", intent="alugar")
    state.set_criterion("budget", 2500)
    missing = missing_critical_fields(state)
    assert missing[0] == "location"
