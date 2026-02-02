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
    # Em modo TRIAGE_ONLY, can_search sempre retorna False
    from agent.rules import TRIAGE_ONLY
    expected = False if TRIAGE_ONLY else True
    assert can_search_properties(state) is expected


def test_missing_critical_fields_order():
    state = SessionState(session_id="s3", intent="alugar")
    state.set_criterion("budget", 2500)
    missing = missing_critical_fields(state)
    # Em modo TRIAGE_ONLY, retorna "city" ao invés de "location"
    # Em modo normal, retorna "location"
    from agent.rules import TRIAGE_ONLY
    expected = "city" if TRIAGE_ONLY else "location"
    assert missing[0] == expected
