"""
TRIAGE_ONLY Anti-Leak Tests

Garantias obrigatórias quando TRIAGE_ONLY=true:
1) Nunca chama tools.search_properties
2) Nunca chama presenter para formatar listagens de venda
3) Nunca retorna action=LIST/SEARCH/REFINE mesmo se LLM retornar
4) Sempre gera resumo final + handoff ao completar campos críticos
"""

import pytest
from unittest.mock import patch, MagicMock

from agent.controller import handle_message
from agent.state import store
from agent import llm as llm_module
from agent import rules as rules_module
from agent import controller as controller_module
from agent import presenter as presenter_module
from agent import tools as tools_module


def triage_patches():
    """Helper para aplicar patches de TRIAGE_ONLY."""
    return [
        patch.object(llm_module, "TRIAGE_ONLY", True),
        patch.object(rules_module, "TRIAGE_ONLY", True),
        patch.object(controller_module, "TRIAGE_ONLY", True),
    ]


def test_triage_never_calls_search_properties():
    """GARANTIA: Em TRIAGE_ONLY, nunca chamar tools.search_properties"""
    session = "anti_leak_1"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.extractor.extract_criteria", return_value={
             "city": "Joao Pessoa",
             "neighborhood": "Manaira",
             "property_type": "apartamento",
             "bedrooms": 2,
             "parking": 1,
             "budget": 3000
         }), \
         patch.object(tools_module, "search_properties") as mock_search, \
         p1, p2, p3:
        # Mesmo com TODOS os campos preenchidos
        resp = handle_message(session, "quero alugar ap 2q em Manaira por 3mil")

    # GARANTIA: search_properties NÃO deve ter sido chamada
    assert mock_search.call_count == 0
    # Não deve retornar properties
    assert "properties" not in resp


def test_triage_never_uses_format_property_list():
    """GARANTIA: Em TRIAGE_ONLY, nunca usar presenter.format_property_list"""
    session = "anti_leak_2"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.extractor.extract_criteria", return_value={
             "city": "Joao Pessoa",
             "property_type": "casa",
             "budget": 5000
         }), \
         patch.object(presenter_module, "format_property_list") as mock_format, \
         patch.object(presenter_module, "format_option") as mock_option, \
         p1, p2, p3:
        resp = handle_message(session, "casa em JP ate 5 mil")

    # GARANTIA: format_property_list e format_option NÃO devem ser chamados
    assert mock_format.call_count == 0
    assert mock_option.call_count == 0


def test_triage_blocks_search_action_from_llm():
    """GARANTIA: Mesmo se LLM retornar action=SEARCH, deve ser bloqueado"""
    session = "anti_leak_3"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    # LLM malicioso retornando SEARCH
    mock_decision = {
        "intent": "alugar",
        "extracted_updates": {
            "city": {"value": "Joao Pessoa", "status": "confirmed"},
            "property_type": {"value": "apartamento", "status": "confirmed"},
            "budget": {"value": 3000, "status": "confirmed"}
        },
        "handoff": {"should": False, "reason": None},
        "plan": {
            "action": "SEARCH",  # ← LLM tentando forçar busca
            "message": "Vou buscar imóveis",
            "filters": {}
        }
    }

    with patch.object(llm_module, "USE_LLM", True), \
         patch.object(llm_module, "LLM_API_KEY", "fake"), \
         patch("agent.llm.llm_decide", return_value=(mock_decision, True)), \
         patch.object(tools_module, "search_properties") as mock_search, \
         p1, p2, p3:
        resp = handle_message(session, "alugar ap em JP")

    # GARANTIA: Deve perguntar próximo campo, não buscar
    assert mock_search.call_count == 0
    assert "properties" not in resp
    # Deve estar perguntando algo ou resumindo
    assert "?" in resp["reply"] or "resumo" in resp["reply"].lower()


def test_triage_generates_summary_when_complete():
    """GARANTIA: Ao completar campos críticos, gerar resumo + handoff"""
    session = "anti_leak_4"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.extractor.extract_criteria", return_value={
             "city": "Joao Pessoa",
             "neighborhood": "Manaira",
             "property_type": "apartamento",
             "bedrooms": 2,
             "parking": 1,
             "budget": 3000,
             "timeline": "imediato"
         }), \
         p1, p2, p3:
        # Primeira mensagem com intent
        handle_message(session, "quero comprar")
        # Segunda mensagem com todos os campos
        resp = handle_message(session, "ap 2q em Manaira JP, 3mil, 1 vaga, imediato")

    # GARANTIA: Deve ter gerado resumo ou handoff
    state = store.get(session)
    # Verifica que completou ou tem handoff
    assert state.completed or "resumo" in resp["reply"].lower() or "handoff" in resp


def test_triage_never_shows_prices():
    """GARANTIA: Nunca usar format_price para mostrar preços de imóveis"""
    session = "anti_leak_5"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.extractor.extract_criteria", return_value={"city": "Recife"}), \
         patch.object(presenter_module, "format_price") as mock_price, \
         p1, p2, p3:
        resp = handle_message(session, "quero ver casas em Recife")

    # GARANTIA: format_price não deve ser chamado
    assert mock_price.call_count == 0


def test_can_search_always_false_in_triage():
    """GARANTIA: can_search_properties sempre retorna False em TRIAGE_ONLY"""
    from agent.rules import can_search_properties
    from agent.state import SessionState

    p1, p2, p3 = triage_patches()
    with p1, p2, p3:
        state = SessionState(session_id="test", intent="alugar")
        state.set_criterion("city", "João Pessoa")
        state.set_criterion("property_type", "apartamento")
        state.set_criterion("budget", 5000)

        # GARANTIA: Mesmo com tudo preenchido, retorna False
        assert can_search_properties(state) is False


def test_triage_guards_against_list_action():
    """GARANTIA: Action LIST também deve ser bloqueada"""
    session = "anti_leak_6"
    store.reset(session)
    p1, p2, p3 = triage_patches()

    mock_decision = {
        "intent": "comprar",
        "extracted_updates": {"city": {"value": "Natal", "status": "confirmed"}},
        "handoff": {"should": False, "reason": None},
        "plan": {"action": "LIST", "message": "Listando imóveis"}  # ← Bloqueado
    }

    with patch.object(llm_module, "USE_LLM", True), \
         patch.object(llm_module, "LLM_API_KEY", "fake"), \
         patch("agent.llm.llm_decide", return_value=(mock_decision, True)), \
         patch.object(tools_module, "search_properties") as mock_search, \
         p1, p2, p3:
        resp = handle_message(session, "quero comprar em Natal")

    # GARANTIA: Não executou LIST
    assert mock_search.call_count == 0
    assert "properties" not in resp


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
