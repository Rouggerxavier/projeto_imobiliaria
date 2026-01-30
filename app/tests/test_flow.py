import os
from unittest.mock import patch

from agent.controller import handle_message
from agent.state import store
from agent import llm as llm_module


def test_happy_path_rent_manaira():
    """Teste com fallback deterministico para comportamento previsivel."""
    session = "t1"
    store.reset(session)

    # Usa fallback para comportamento determinístico
    with patch.object(llm_module, 'USE_LLM', False):
        resp = handle_message(session, "quero alugar um ape em Manaira ate 3 mil, 2 quartos")

    assert resp["state"]["intent"] == "alugar"
    # Com fallback, deve fazer SEARCH e retornar propriedades
    assert resp.get("properties") or "orcamento" in resp["reply"].lower() or "opcoes" in resp["reply"].lower()


def test_missing_location_triggers_question():
    """Teste que pergunta localização quando falta."""
    session = "t2"
    store.reset(session)

    with patch.object(llm_module, 'USE_LLM', False):
        resp = handle_message(session, "quero alugar por 2000 um apartamento")

    # Deve perguntar sobre localização ou cidade
    reply_lower = resp["reply"].lower()
    assert "cidade" in reply_lower or "bairro" in reply_lower or "localiza" in reply_lower


def test_zero_results_handles_gracefully():
    """Teste que lida bem com zero resultados."""
    import unicodedata

    def strip_accents(text: str) -> str:
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    session = "t3"
    store.reset(session)

    with patch.object(llm_module, 'USE_LLM', False):
        # Orcamento muito baixo para encontrar algo
        resp = handle_message(session, "quero alugar casa em Manaira ate 100 reais")

    # Deve informar que nao encontrou ou pedir para refinar
    reply_lower = strip_accents(resp["reply"].lower())
    assert ("nao encontrei" in reply_lower or
            "orcamento" in reply_lower or
            "refinar" in reply_lower or
            "opcoes" in reply_lower)
