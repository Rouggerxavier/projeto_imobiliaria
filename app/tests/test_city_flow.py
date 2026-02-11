import unicodedata
from unittest.mock import patch

from agent.controller import handle_message
from agent.state import store
from agent import llm as llm_module
from agent import rules as rules_module
from agent import controller as controller_module


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()


def triage_patches():
    return [
        patch.object(llm_module, "TRIAGE_ONLY", True),
        patch.object(rules_module, "TRIAGE_ONLY", True),
        patch.object(controller_module, "TRIAGE_ONLY", True),
    ]


def test_city_question_is_neutral():
    session = "city_flow_1"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    with patch.object(llm_module, "USE_LLM", False), p1, p2, p3:
        resp = handle_message(session, "quero comprar um apartamento")

    reply_norm = _normalize(resp["reply"])
    assert "padrao" not in reply_norm
    assert ("joao pessoa" in reply_norm and "cabedelo" in reply_norm) or "cidade" in reply_norm
    assert "bairro" not in reply_norm


def test_city_response_updates_state_and_neighborhood_uses_city():
    session = "city_flow_2"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    with patch.object(llm_module, "USE_LLM", False), p1, p2, p3:
        handle_message(session, "quero comprar um apartamento")
        resp = handle_message(session, "Cabedelo")

    assert resp["state"]["criteria"]["city"] == "Cabedelo"
    reply_norm = _normalize(resp["reply"])
    assert "cabedelo" in reply_norm
    assert "joao pessoa" not in reply_norm
    assert "bairro" in reply_norm


def test_city_joao_pessoa_flows_to_neighborhood():
    session = "city_flow_3"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    with patch.object(llm_module, "USE_LLM", False), p1, p2, p3:
        handle_message(session, "quero comprar um apartamento")
        resp = handle_message(session, "João Pessoa")

    assert resp["state"]["criteria"]["city"] == "Joao Pessoa"
    reply_norm = _normalize(resp["reply"])
    assert "joao pessoa" in reply_norm
    assert "cabedelo" not in reply_norm
    assert "bairro" in reply_norm
