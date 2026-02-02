import pytest
from unittest.mock import patch

from agent.controller import handle_message
from agent.state import store
from agent import llm as llm_module
from agent import rules as rules_module
from agent import controller as controller_module


def triage_patches():
    return [
        patch.object(llm_module, "TRIAGE_ONLY", True),
        patch.object(rules_module, "TRIAGE_ONLY", True),
        patch.object(controller_module, "TRIAGE_ONLY", True),
    ]


def test_budget_not_repeated_after_confirmed():
    session = "triage_budget"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.extractor.extract_criteria", return_value={
             "city": "Joao Pessoa",
             "neighborhood": "Manaira",
             "budget": 800000,
             "property_type": "apartamento",
             "bedrooms": 3,
             "parking": 2
         }), \
         p1, p2, p3:
        resp = handle_message(session, "quero comprar em Manaira, orcamento 800 mil, 3 quartos e 2 vagas")

    assert "orcamento" not in resp["reply"].lower()


def test_triage_only_never_searches_properties():
    session = "triage_no_search"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    mock_decision = {
        "intent": "alugar",
        "extracted_updates": {
            "city": {"value": "Joao Pessoa", "status": "confirmed"},
            "neighborhood": {"value": "Manaira", "status": "confirmed"},
            "property_type": {"value": "apartamento", "status": "confirmed"},
            "bedrooms": {"value": 2, "status": "confirmed"},
            "parking": {"value": 1, "status": "confirmed"},
            "budget": {"value": 3000, "status": "confirmed"},
        },
        "handoff": {"should": False, "reason": None},
        "plan": {"action": "ASK", "question_key": "timeline", "message": "Qual o prazo para mudar?"}
    }

    with patch.object(llm_module, "USE_LLM", True), \
         patch.object(llm_module, "LLM_API_KEY", "fake"), \
         patch.object(llm_module, "call_llm", return_value=mock_decision), \
         patch("agent.tools.search_properties") as mock_search, \
         p1, p2, p3:
        resp = handle_message(session, "quero alugar ap em Manaira")

    assert mock_search.call_count == 0
    assert "properties" not in resp


def test_multi_info_extract_advances_to_next_field():
    """Teste que quando extrai múltiplos campos, avança para o próximo campo faltante."""
    session = "triage_multi"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    # Com USE_LLM=False, usa extractor determinístico que captura os campos
    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.extractor.extract_criteria", return_value={
             "neighborhood": "Manaira",
             "bedrooms": 4,
             "parking": 2,
             "budget": 800000
         }), \
         p1, p2, p3:
        # Primeira mensagem - sem intent
        resp = handle_message(session, "Manaira, 4 quartos, 800 mil, 2 vagas")
        # Deve perguntar intent
        assert "comprar" in resp["reply"].lower() or "alugar" in resp["reply"].lower()

    p4, p5, p6 = triage_patches()
    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.extractor.extract_criteria", return_value={
             "city": "Joao Pessoa"
         }), \
         p4, p5, p6:
        # Segunda mensagem - fornece intent e city
        resp2 = handle_message(session, "comprar em Joao Pessoa")
        # Deve pedir property_type
        assert "tipo" in resp2["reply"].lower() or "apartamento" in resp2["reply"].lower() or "casa" in resp2["reply"].lower()


def test_contradiction_triggers_clarify():
    session = "triage_conflict"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.extractor.extract_criteria", return_value={
             "city": "Joao Pessoa",
             "neighborhood": "Manaira",
             "budget": 800000,
             "property_type": "apartamento"
         }), \
         p1, p2, p3:
        handle_message(session, "Quero comprar em Manaira ate 800 mil")

    p4, p5, p6 = triage_patches()
    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.extractor.extract_criteria", return_value={
             "budget": 600000
         }), \
         p4, p5, p6:
        resp = handle_message(session, "pensando em ate 600 mil")

    reply_lower = resp["reply"].lower()
    assert "800" in reply_lower and "600" in reply_lower
