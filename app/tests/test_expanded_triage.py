"""
Testes para Fluxo de Triagem Expandido

Valida que o bot coleta corretamente os novos campos obrigatórios:
- suites
- bathrooms_min
- micro_location (beach proximity)
- leisure_required
- leisure_level

E aceita "indifferent/tanto faz" como valor válido.
"""

import pytest
from app.agent.state import SessionState, store
from app.agent.controller import handle_message
from app.agent.rules import missing_critical_fields


@pytest.fixture
def session_id():
    """Cria uma sessão de teste única."""
    sid = "test_expanded_triage_001"
    store.reset(sid)
    return sid


def test_suites_required_not_finalize_without_it(session_id):
    """Bot NÃO encerra triagem sem registrar suites (mesmo que 'indiferente')."""
    # Simula fluxo até bedrooms (antes de suites)
    handle_message(session_id, "Quero alugar um apartamento")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Manaíra")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "3 quartos")

    state = store.get(session_id)
    missing = missing_critical_fields(state)

    # Suites deve estar na lista de missing
    assert "suites" in missing, "Suites deve ser campo obrigatório"


def test_suites_indifferent_completes_field(session_id):
    """Usuário responde 'tanto faz' para suítes e isso completa o campo."""
    handle_message(session_id, "Quero alugar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Manaíra")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "3 quartos")

    # Pergunta suites
    response = handle_message(session_id, "tanto faz")
    state = store.get(session_id)

    # Verifica que suites foi preenchida como "indifferent"
    suites_data = state.triage_fields.get("suites")
    assert suites_data is not None, "Suites deve estar preenchida"
    assert suites_data.get("value") == "indifferent", "Suites deve ser 'indifferent'"

    # Suites NÃO deve mais estar em missing
    missing = missing_critical_fields(state)
    assert "suites" not in missing, "Suites 'indifferent' deve contar como preenchido"


def test_bathrooms_required(session_id):
    """Bot coleta banheiros após suítes."""
    handle_message(session_id, "Quero comprar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Bessa")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "2 quartos")
    handle_message(session_id, "1 suíte")

    state = store.get(session_id)
    missing = missing_critical_fields(state)

    # bathrooms_min deve estar na lista de missing
    assert "bathrooms_min" in missing, "bathrooms_min deve ser campo obrigatório"


def test_bathrooms_indifferent_accepted(session_id):
    """Usuário responde 'tanto faz' para banheiros."""
    handle_message(session_id, "Quero comprar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Bessa")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "2 quartos")
    handle_message(session_id, "1 suíte")

    # Responde "tanto faz" para banheiros
    handle_message(session_id, "tanto faz")

    state = store.get(session_id)
    bathrooms_data = state.triage_fields.get("bathrooms_min")

    assert bathrooms_data is not None
    assert bathrooms_data.get("value") == "indifferent"

    missing = missing_critical_fields(state)
    assert "bathrooms_min" not in missing


def test_beach_proximity_required(session_id):
    """Bot pergunta proximidade da praia (micro_location)."""
    handle_message(session_id, "Alugar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Manaíra")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "3 quartos")
    handle_message(session_id, "2 suítes")
    handle_message(session_id, "2 banheiros")
    handle_message(session_id, "2 vagas")
    handle_message(session_id, "até 1 milhão")
    handle_message(session_id, "3 meses")

    state = store.get(session_id)
    missing = missing_critical_fields(state)

    assert "micro_location" in missing


def test_beach_proximity_beira_mar(session_id):
    """Usuário diz 'beira-mar' e sistema captura."""
    handle_message(session_id, "Comprar apartamento em Manaíra, João Pessoa")
    handle_message(session_id, "3 quartos")
    handle_message(session_id, "nenhuma suíte")
    handle_message(session_id, "2 banheiros")
    handle_message(session_id, "2 vagas")
    handle_message(session_id, "800 mil")
    handle_message(session_id, "30 dias")

    # Responde sobre praia
    handle_message(session_id, "beira-mar")

    state = store.get(session_id)
    micro_loc = state.triage_fields.get("micro_location", {}).get("value")

    assert micro_loc == "beira-mar"


def test_leisure_required(session_id):
    """Bot pergunta sobre área de lazer."""
    handle_message(session_id, "Quero alugar")
    handle_message(session_id, "Cabedelo")
    handle_message(session_id, "Intermares")
    handle_message(session_id, "Casa")
    handle_message(session_id, "2 quartos")
    handle_message(session_id, "0 suítes")
    handle_message(session_id, "1 banheiro")
    handle_message(session_id, "1 vaga")
    handle_message(session_id, "2 mil por mês")
    handle_message(session_id, "6 meses")
    handle_message(session_id, "tanto faz praia")

    state = store.get(session_id)
    missing = missing_critical_fields(state)

    assert "leisure_required" in missing


def test_leisure_indifferent_accepted(session_id):
    """Usuário diz 'tanto faz' para lazer."""
    handle_message(session_id, "Quero comprar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Manaíra")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "2 quartos")
    handle_message(session_id, "tanto faz suíte")
    handle_message(session_id, "indiferente banheiro")
    handle_message(session_id, "1 vaga")
    handle_message(session_id, "500 mil")
    handle_message(session_id, "flexível")
    handle_message(session_id, "tanto faz")  # praia

    # Responde sobre lazer
    handle_message(session_id, "indiferente")

    state = store.get(session_id)
    leisure_req = state.triage_fields.get("leisure_required", {}).get("value")

    assert leisure_req == "indifferent"

    missing = missing_critical_fields(state)
    assert "leisure_required" not in missing


def test_confusion_handling_suites(session_id):
    """Usuário pergunta 'suíte como assim?' e bot explica sem avançar."""
    handle_message(session_id, "Alugar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Tambaú")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "3 quartos")

    # Pergunta sobre suítes (confusão)
    response = handle_message(session_id, "suíte como assim?")

    # Verifica que a resposta contém explicação
    assert "suíte" in response["reply"].lower() or "banheiro" in response["reply"].lower()

    state = store.get(session_id)

    # Não deve ter avançado (suites ainda missing)
    missing = missing_critical_fields(state)
    assert "suites" in missing


def test_combined_extraction_suites_bathrooms(session_id):
    """Usuário responde suítes e banheiros na mesma mensagem."""
    handle_message(session_id, "Comprar")
    handle_message(session_id, "João Pessoa")
    handle_message(session_id, "Manaíra")
    handle_message(session_id, "Apartamento")
    handle_message(session_id, "3 quartos")

    # Responde sobre suítes e banheiros juntos
    handle_message(session_id, "2 suítes e 3 banheiros no total")

    state = store.get(session_id)

    suites = state.triage_fields.get("suites", {}).get("value")
    bathrooms = state.triage_fields.get("bathrooms_min", {}).get("value")

    assert suites == 2
    assert bathrooms == 3


def test_degraded_mode_still_collects_fields(session_id):
    """Em modo degradado (sem LLM), bot ainda coleta os novos campos via regex."""
    # Força degraded mode
    state = store.get(session_id)
    state.llm_degraded = True

    handle_message(session_id, "Quero alugar apartamento em Manaíra, João Pessoa")
    handle_message(session_id, "3 quartos")
    handle_message(session_id, "2 suítes")
    handle_message(session_id, "3 banheiros")
    handle_message(session_id, "2 vagas")
    handle_message(session_id, "até 1 milhão")
    handle_message(session_id, "30 dias")
    handle_message(session_id, "beira-mar")
    handle_message(session_id, "sim, área de lazer completa")

    state = store.get(session_id)

    # Verifica que campos foram extraídos
    assert state.criteria.suites == 2
    assert state.criteria.bathrooms_min == 3
    assert "beira-mar" in str(state.criteria.micro_location)
    assert state.triage_fields.get("leisure_required", {}).get("value") in ["yes", "indifferent"]


def test_full_flow_with_all_new_fields(session_id):
    """Fluxo completo coletando todos os novos campos."""
    handle_message(session_id, "Quero comprar um apartamento")
    response = handle_message(session_id, "João Pessoa")
    response = handle_message(session_id, "Manaíra")
    response = handle_message(session_id, "Apartamento")
    response = handle_message(session_id, "3 quartos")
    response = handle_message(session_id, "2 suítes")
    response = handle_message(session_id, "3 banheiros")
    response = handle_message(session_id, "2 vagas")
    response = handle_message(session_id, "entre 800 mil e 1.2 milhão")
    response = handle_message(session_id, "30 dias")
    response = handle_message(session_id, "beira-mar")
    response = handle_message(session_id, "sim, área de lazer completa")
    response = handle_message(session_id, "João Silva")
    response = handle_message(session_id, "83 98888-7777")

    state = store.get(session_id)

    # Verifica todos os campos críticos foram preenchidos
    missing = missing_critical_fields(state)
    assert len(missing) == 0, f"Não deveria ter campos faltando: {missing}"

    # Verifica que completed foi setado
    assert state.completed is True, "Triagem deveria estar completa"

    # Verifica resumo contém os novos campos
    assert "reply" in response
    reply = response["reply"]
    assert "suíte" in reply.lower() or "suite" in reply.lower()
    assert "banheiro" in reply.lower()
    assert "praia" in reply.lower() or "beira-mar" in reply.lower()
    assert "lazer" in reply.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
