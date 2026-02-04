"""
Testes para Quality Score - Avaliação de completude e confiança do lead.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.quality import compute_quality_score
from agent.state import SessionState, LeadScore


def test_perfect_lead_grade_a():
    """Lead completo e confirmado deve ter grade A."""
    state = SessionState(session_id="test_perfect")
    state.intent = "comprar"
    state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
    state.set_triage_field("neighborhood", "Manaíra", status="confirmed", source="user")
    state.set_triage_field("property_type", "apartamento", status="confirmed", source="user")
    state.set_triage_field("bedrooms", 3, status="confirmed", source="user")
    state.set_triage_field("parking", 2, status="confirmed", source="user")
    state.set_triage_field("budget", 1000000, status="confirmed", source="user")
    state.set_triage_field("timeline", "3m", status="confirmed", source="user")
    state.set_triage_field("micro_location", "beira-mar", status="confirmed", source="user")
    state.set_triage_field("suites", 2, status="confirmed", source="user")
    state.lead_profile["name"] = "João Silva"

    result = compute_quality_score(state)

    assert result["grade"] == "A", f"Expected grade A, got {result['grade']}"
    assert result["score"] >= 85, f"Expected score >= 85, got {result['score']}"
    assert result["completeness"] == 1.0, "All critical fields should be filled"
    assert result["confidence"] == 1.0, "All fields should be confirmed"
    assert "missing_critical" not in str(result["reasons"]), "Should not have missing critical fields"


def test_missing_critical_fields_low_score():
    """Faltando campos críticos deve resultar em score baixo e grade ruim."""
    state = SessionState(session_id="test_missing")
    state.intent = "alugar"
    # Só preenche intent e cidade
    state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")

    result = compute_quality_score(state)

    assert result["grade"] in ["C", "D"], f"Expected grade C or D, got {result['grade']}"
    assert result["score"] < 50, f"Expected score < 50, got {result['score']}"
    assert "missing_critical" in str(result["reasons"]), "Should have missing critical fields"
    assert result["completeness"] < 0.5, "Completeness should be low"


def test_many_inferred_penalizes():
    """Muitos campos inferred devem penalizar o score."""
    state = SessionState(session_id="test_inferred")
    state.intent = "comprar"
    state.set_triage_field("city", "Joao Pessoa", status="inferred", source="llm")
    state.set_triage_field("neighborhood", "Tambaú", status="inferred", source="llm")
    state.set_triage_field("property_type", "casa", status="inferred", source="llm")
    state.set_triage_field("bedrooms", 2, status="confirmed", source="user")
    state.set_triage_field("parking", 1, status="confirmed", source="user")
    state.set_triage_field("budget", 500000, status="confirmed", source="user")
    state.set_triage_field("timeline", "6m", status="confirmed", source="user")

    result = compute_quality_score(state)

    # Deve ter completude boa mas confiança média
    assert result["completeness"] == 1.0, "All fields filled"
    assert result["confidence"] < 1.0, "Not all fields confirmed"
    assert "inferred" in str(result["reasons"]), "Should mention inferred fields"
    assert result["grade"] in ["B", "C"], f"Expected grade B or C, got {result['grade']}"


def test_unresolved_conflict_heavy_penalty():
    """Conflito pendente deve penalizar fortemente."""
    state = SessionState(session_id="test_conflict")
    state.intent = "alugar"
    state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
    state.set_triage_field("neighborhood", "Manaíra", status="confirmed", source="user")
    state.set_triage_field("property_type", "apartamento", status="confirmed", source="user")
    state.set_triage_field("bedrooms", 2, status="confirmed", source="user")
    state.set_triage_field("parking", 1, status="confirmed", source="user")
    state.set_triage_field("budget", 3000, status="confirmed", source="user")
    state.set_triage_field("timeline", "3m", status="confirmed", source="user")

    # Adiciona mensagem de conflito no histórico
    state.history.append({
        "role": "assistant",
        "text": "Notei duas respostas diferentes para budget: 3000 vs 3500. Qual vale?"
    })

    result = compute_quality_score(state)

    assert "unresolved_conflict" in result["reasons"], "Should detect conflict"
    assert result["score"] < 90, f"Conflict should reduce score, got {result['score']}"
    assert result["grade"] in ["B", "C"], f"Conflict should reduce grade, got {result['grade']}"


def test_micro_location_orla_ambiguous():
    """Micro-location 'orla' sem confirmação deve penalizar."""
    state = SessionState(session_id="test_orla")
    state.intent = "comprar"
    state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
    state.set_triage_field("neighborhood", "Cabo Branco", status="confirmed", source="user")
    state.set_triage_field("property_type", "apartamento", status="confirmed", source="user")
    state.set_triage_field("bedrooms", 3, status="confirmed", source="user")
    state.set_triage_field("parking", 2, status="confirmed", source="user")
    state.set_triage_field("budget", 800000, status="confirmed", source="user")
    state.set_triage_field("timeline", "6m", status="confirmed", source="user")
    state.set_triage_field("micro_location", "orla", status="inferred", source="llm")

    result = compute_quality_score(state)

    assert "micro_location_ambiguous" in result["reasons"], "Orla should be flagged as ambiguous"
    assert result["score"] < 100, "Should penalize orla"


def test_missing_condo_max_high_budget():
    """Budget alto sem condo_max deve penalizar."""
    state = SessionState(session_id="test_condo")
    state.intent = "comprar"
    state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
    state.set_triage_field("neighborhood", "Manaíra", status="confirmed", source="user")
    state.set_triage_field("property_type", "apartamento", status="confirmed", source="user")
    state.set_triage_field("bedrooms", 3, status="confirmed", source="user")
    state.set_triage_field("parking", 2, status="confirmed", source="user")
    state.set_triage_field("budget", 1500000, status="confirmed", source="user")  # Alto
    state.set_triage_field("timeline", "3m", status="confirmed", source="user")
    # condo_max ausente

    result = compute_quality_score(state)

    assert "missing_condo_max_high_budget" in result["reasons"], "Should flag missing condo_max"


def test_missing_payment_type_compra():
    """Compra sem payment_type deve penalizar."""
    state = SessionState(session_id="test_payment")
    state.intent = "comprar"  # Compra
    state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
    state.set_triage_field("neighborhood", "Tambaú", status="confirmed", source="user")
    state.set_triage_field("property_type", "casa", status="confirmed", source="user")
    state.set_triage_field("bedrooms", 3, status="confirmed", source="user")
    state.set_triage_field("parking", 2, status="confirmed", source="user")
    state.set_triage_field("budget", 600000, status="confirmed", source="user")
    state.set_triage_field("timeline", "6m", status="confirmed", source="user")
    # payment_type ausente

    result = compute_quality_score(state)

    assert "missing_payment_type" in result["reasons"], "Should flag missing payment_type for compra"


def test_budget_inconsistent():
    """Budget_min > Budget_max deve penalizar."""
    state = SessionState(session_id="test_budget_inconsistent")
    state.intent = "comprar"
    state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
    state.set_triage_field("neighborhood", "Manaíra", status="confirmed", source="user")
    state.set_triage_field("property_type", "apartamento", status="confirmed", source="user")
    state.set_triage_field("bedrooms", 2, status="confirmed", source="user")
    state.set_triage_field("parking", 1, status="confirmed", source="user")
    state.set_triage_field("budget", 500000, status="confirmed", source="user")  # max
    state.set_triage_field("budget_min", 600000, status="confirmed", source="user")  # min > max!
    state.set_triage_field("timeline", "3m", status="confirmed", source="user")

    result = compute_quality_score(state)

    assert "budget_inconsistent" in result["reasons"], "Should detect budget inconsistency"


def test_bonus_for_extras():
    """Campos extras bem definidos devem dar bônus."""
    state = SessionState(session_id="test_bonus")
    state.intent = "alugar"
    state.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")
    state.set_triage_field("neighborhood", "Manaíra", status="confirmed", source="user")
    state.set_triage_field("property_type", "apartamento", status="confirmed", source="user")
    state.set_triage_field("bedrooms", 3, status="confirmed", source="user")
    state.set_triage_field("parking", 2, status="confirmed", source="user")
    state.set_triage_field("budget", 4000, status="confirmed", source="user")
    state.set_triage_field("timeline", "3m", status="confirmed", source="user")  # Específico, não flexível
    state.set_triage_field("micro_location", "beira-mar", status="confirmed", source="user")  # Confirmado
    state.set_triage_field("suites", 1, status="confirmed", source="user")
    state.lead_profile["name"] = "Ana Costa"

    result = compute_quality_score(state)

    assert "micro_location_confirmed" in result["reasons"], "Should bonus confirmed micro_location"
    assert "suites_defined" in result["reasons"], "Should bonus suites"
    assert "name_available" in result["reasons"], "Should bonus name"
    assert "timeline_specific" in result["reasons"], "Should bonus specific timeline"
    assert result["score"] > 90, f"Should have high score with bonuses, got {result['score']}"


def test_grade_boundaries():
    """Testa boundaries de grades."""
    # Grade A: >= 85
    state_a = SessionState(session_id="grade_a")
    state_a.intent = "comprar"
    for field in ["city", "neighborhood", "property_type", "bedrooms", "parking", "budget", "timeline"]:
        state_a.set_triage_field(field, "value", status="confirmed", source="user")

    result_a = compute_quality_score(state_a)
    if result_a["score"] >= 85:
        assert result_a["grade"] == "A"

    # Grade D: < 50
    state_d = SessionState(session_id="grade_d")
    state_d.intent = "alugar"
    # Apenas 1 campo
    state_d.set_triage_field("city", "Joao Pessoa", status="confirmed", source="user")

    result_d = compute_quality_score(state_d)
    assert result_d["score"] < 50
    assert result_d["grade"] == "D"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
