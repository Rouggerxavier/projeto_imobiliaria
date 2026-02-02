"""
State Conflict Detection Tests

Testa o método SessionState.apply_updates para garantir:
1) Detecta conflitos entre valores confirmed
2) Não sobrescreve valores confirmed sem confirmação
3) Permite upgrade de inferred para confirmed
4) Retorna conflitos com valores previous/new
"""

import pytest
from agent.state import SessionState, store


def test_conflict_detection_confirmed_vs_confirmed():
    """Conflito quando tentar mudar valor confirmed por outro confirmed."""
    state = SessionState(session_id="conflict_1")

    # Primeiro update: budget confirmed
    updates1 = {"budget": {"value": 500000, "status": "confirmed"}}
    conflicts1, values1 = state.apply_updates(updates1)

    assert len(conflicts1) == 0
    assert state.criteria.budget == 500000
    assert state.get_criterion_status("budget") == "confirmed"

    # Segundo update: tentar mudar budget confirmed
    updates2 = {"budget": {"value": 700000, "status": "confirmed"}}
    conflicts2, values2 = state.apply_updates(updates2)

    # GARANTIA: Deve detectar conflito
    assert "budget" in conflicts2
    assert values2["budget"]["previous"] == 500000
    assert values2["budget"]["new"] == 700000
    # Não deve ter sobrescrito
    assert state.criteria.budget == 500000


def test_no_conflict_inferred_to_confirmed():
    """Não há conflito ao upgradar inferred para confirmed."""
    state = SessionState(session_id="upgrade_1")

    # Primeiro: valor inferred
    updates1 = {"city": {"value": "Recife", "status": "inferred"}}
    conflicts1, _ = state.apply_updates(updates1)

    assert len(conflicts1) == 0
    assert state.criteria.city == "Recife"
    assert state.get_criterion_status("city") == "inferred"

    # Segundo: usuário confirma
    updates2 = {"city": {"value": "Recife", "status": "confirmed"}}
    conflicts2, _ = state.apply_updates(updates2)

    # GARANTIA: Não deve ter conflito
    assert len(conflicts2) == 0
    assert state.criteria.city == "Recife"
    assert state.get_criterion_status("city") == "confirmed"


def test_conflict_intent_change():
    """Conflito ao mudar intent de comprar para alugar."""
    state = SessionState(session_id="intent_conflict")
    state.intent = "comprar"

    # Tentar mudar para alugar
    updates = {"intent": {"value": "alugar", "status": "confirmed"}}
    conflicts, values = state.apply_updates(updates)

    # GARANTIA: Deve detectar conflito
    assert "intent" in conflicts
    assert values["intent"]["previous"] == "comprar"
    assert values["intent"]["new"] == "alugar"
    # Intent não deve ter mudado
    assert state.intent == "comprar"


def test_no_conflict_same_value():
    """Não há conflito se valor é o mesmo."""
    state = SessionState(session_id="same_value")

    updates1 = {"bedrooms": {"value": 3, "status": "confirmed"}}
    state.apply_updates(updates1)

    updates2 = {"bedrooms": {"value": 3, "status": "confirmed"}}
    conflicts, _ = state.apply_updates(updates2)

    # GARANTIA: Mesmo valor não gera conflito
    assert len(conflicts) == 0
    assert state.criteria.bedrooms == 3


def test_multiple_conflicts_same_update():
    """Múltiplos conflitos no mesmo update."""
    state = SessionState(session_id="multi_conflict")

    # Setup inicial
    updates1 = {
        "budget": {"value": 300000, "status": "confirmed"},
        "bedrooms": {"value": 2, "status": "confirmed"}
    }
    state.apply_updates(updates1)

    # Tentar mudar ambos
    updates2 = {
        "budget": {"value": 400000, "status": "confirmed"},
        "bedrooms": {"value": 3, "status": "confirmed"}
    }
    conflicts, values = state.apply_updates(updates2)

    # GARANTIA: Detectar ambos conflitos
    assert len(conflicts) == 2
    assert "budget" in conflicts
    assert "bedrooms" in conflicts
    assert values["budget"]["previous"] == 300000
    assert values["budget"]["new"] == 400000
    assert values["bedrooms"]["previous"] == 2
    assert values["bedrooms"]["new"] == 3
    # Valores não mudaram
    assert state.criteria.budget == 300000
    assert state.criteria.bedrooms == 2


def test_no_overwrite_on_conflict():
    """Garantir que conflitos não sobrescrevem valores."""
    state = SessionState(session_id="no_overwrite")

    # Valor inicial
    updates1 = {"property_type": {"value": "apartamento", "status": "confirmed"}}
    state.apply_updates(updates1)
    original = state.criteria.property_type

    # Conflito
    updates2 = {"property_type": {"value": "casa", "status": "confirmed"}}
    conflicts, _ = state.apply_updates(updates2)

    # GARANTIA: Valor permanece o original
    assert state.criteria.property_type == original
    assert state.criteria.property_type == "apartamento"
    assert "property_type" in conflicts


def test_mixed_conflicts_and_updates():
    """Updates parciais: alguns conflitam, outros não."""
    state = SessionState(session_id="mixed")

    # Setup
    updates1 = {
        "city": {"value": "Joao Pessoa", "status": "confirmed"},
        "budget": {"value": 200000, "status": "inferred"}
    }
    state.apply_updates(updates1)

    # Update misto
    updates2 = {
        "city": {"value": "Recife", "status": "confirmed"},  # ← Conflito
        "budget": {"value": 200000, "status": "confirmed"},  # ← Upgrade OK
        "bedrooms": {"value": 2, "status": "confirmed"}      # ← Novo OK
    }
    conflicts, values = state.apply_updates(updates2)

    # GARANTIA: Só city conflita
    assert len(conflicts) == 1
    assert "city" in conflicts
    assert state.criteria.city == "Joao Pessoa"  # Não mudou
    # Budget foi upgradado
    assert state.criteria.budget == 200000
    assert state.get_criterion_status("budget") == "confirmed"
    # Bedrooms foi adicionado
    assert state.criteria.bedrooms == 2


def test_triage_fields_sync_with_criteria():
    """Garantir que triage_fields sincroniza com criteria."""
    state = SessionState(session_id="sync")

    updates = {
        "city": {"value": "Natal", "status": "confirmed"},
        "budget": {"value": 500000, "status": "inferred"}
    }
    state.apply_updates(updates)

    # GARANTIA: Ambos devem estar em sync
    assert state.triage_fields["city"]["value"] == "Natal"
    assert state.triage_fields["city"]["status"] == "confirmed"
    assert state.criteria.city == "Natal"

    assert state.triage_fields["budget"]["value"] == 500000
    assert state.triage_fields["budget"]["status"] == "inferred"
    assert state.criteria.budget == 500000


def test_controller_uses_apply_updates():
    """Garantir que controller usa state.apply_updates ao invés de lógica local."""
    from unittest.mock import patch
    from agent.controller import handle_message
    from agent import llm as llm_module

    session = "controller_apply"
    store.reset(session)

    with patch.object(llm_module, "USE_LLM", False), \
         patch("agent.extractor.extract_criteria", return_value={
             "city": "Joao Pessoa",
             "budget": 300000
         }):
        resp = handle_message(session, "quero alugar em JP ate 300 mil")

    state = store.get(session)

    # GARANTIA: state.apply_updates foi usado (triage_fields preenchido)
    assert "city" in state.triage_fields
    assert "budget" in state.triage_fields
    assert state.triage_fields["city"]["value"] == "Joao Pessoa"
    assert state.triage_fields["budget"]["value"] == 300000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
