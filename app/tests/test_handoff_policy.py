from agent.controller import handle_message
from agent.state import store


def test_no_handoff_on_partial_criteria():
    session = "t_partial"
    store.reset(session)
    resp = handle_message(session, "queria um ap em joao pessoa")
    assert resp["state"]["human_handoff"] is False
    # Must ask about intent (order of words may vary)
    reply_lower = resp["reply"].lower()
    assert ("alugar" in reply_lower and "comprar" in reply_lower) or "inten" in reply_lower


def test_handoff_on_visit_request():
    session = "t_visit"
    store.reset(session)
    resp = handle_message(session, "quero visitar amanha")
    assert resp["state"]["human_handoff"] is True


def test_handoff_on_negotiation():
    session = "t_negociation"
    store.reset(session)
    resp = handle_message(session, "consegue baixar o preco?")
    assert resp["state"]["human_handoff"] is True


def test_question_policy_single_question():
    session = "t_single_q"
    store.reset(session)
    resp = handle_message(session, "quero um ap")
    assert resp["reply"].count("?") == 1
