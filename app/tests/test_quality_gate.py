"""
Testes para Quality Gate - Controle de handoff baseado em quality_score
"""

import pytest
from app.agent.state import SessionState
from app.agent.quality_gate import (
    should_handoff,
    identify_quality_gaps,
    next_question_from_quality_gaps,
    detect_field_refusal,
    mark_field_refusal,
    MAX_QUALITY_GATE_TURNS,
)
from app.agent.quality import compute_quality_score


def test_should_handoff_with_high_quality_score():
    """
    Cenário 1: quality_score A ou B deve permitir handoff.
    """
    state = SessionState(session_id="test-1")
    state.intent = "comprar"
    state.set_criterion("city", "João Pessoa", status="confirmed")
    state.set_criterion("neighborhood", "Manaíra", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="confirmed")
    state.set_criterion("bedrooms", 3, status="confirmed")
    state.set_criterion("parking", 2, status="confirmed")
    state.set_criterion("budget", 800000, status="confirmed")
    state.set_criterion("timeline", "3m", status="confirmed")
    state.set_criterion("micro_location", "beira-mar", status="confirmed")
    state.lead_profile["name"] = "João Silva"

    quality = compute_quality_score(state)

    # Quality score deve ser A ou B
    assert quality["grade"] in {"A", "B"}, f"Expected A or B, got {quality['grade']}"

    # Should handoff deve retornar True
    assert should_handoff(state, quality) is True


def test_should_not_handoff_with_low_quality_and_missing_fields():
    """
    Cenário 2: quality_score C/D com campo crítico faltando deve bloquear handoff.
    """
    state = SessionState(session_id="test-2")
    state.intent = "alugar"
    state.set_criterion("city", "João Pessoa", status="inferred")
    state.set_criterion("neighborhood", "Tambaú", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="confirmed")
    state.set_criterion("bedrooms", 2, status="confirmed")
    # Faltando: parking, budget (críticos)
    state.set_criterion("timeline", "flexivel", status="confirmed")

    quality = compute_quality_score(state)

    # Quality score deve ser C ou D (campos críticos faltando)
    assert quality["grade"] in {"C", "D"}, f"Expected C or D, got {quality['grade']}"

    # Should handoff deve retornar False (bloquear)
    assert should_handoff(state, quality) is False

    # Deve retornar uma pergunta relevante
    next_key = next_question_from_quality_gaps(state, quality)
    assert next_key in {"parking", "budget"}, f"Expected parking or budget, got {next_key}"


def test_should_handoff_after_max_quality_gate_turns():
    """
    Cenário 3: Após MAX_QUALITY_GATE_TURNS perguntas, deve permitir handoff mesmo com C/D.
    """
    state = SessionState(session_id="test-3")
    state.intent = "comprar"
    state.set_criterion("city", "João Pessoa", status="inferred")
    state.set_criterion("neighborhood", "Cabo Branco", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="confirmed")
    state.set_criterion("bedrooms", 2, status="confirmed")
    state.set_criterion("parking", 1, status="inferred")
    state.set_criterion("budget", 600000, status="confirmed")
    state.set_criterion("timeline", "6m", status="confirmed")

    # Simular que já foram feitas MAX_QUALITY_GATE_TURNS perguntas de gate
    state.quality_gate_turns = MAX_QUALITY_GATE_TURNS

    quality = compute_quality_score(state)

    # Quality score pode ser C (campos inferred)
    # Mas should handoff deve retornar True por ter atingido limite
    assert should_handoff(state, quality) is True


def test_should_not_repeat_refused_field():
    """
    Cenário 4: Campo recusado pelo usuário não deve ser perguntado novamente.
    """
    state = SessionState(session_id="test-4")
    state.intent = "comprar"  # Compra precisa payment_type (dealbreaker)
    state.set_criterion("city", "João Pessoa", status="confirmed")
    state.set_criterion("neighborhood", "Bessa", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="confirmed")
    state.set_criterion("bedrooms", 3, status="confirmed")
    state.set_criterion("parking", 2, status="confirmed")
    state.set_criterion("budget", 800000, status="confirmed")
    state.set_criterion("timeline", "30d", status="confirmed")
    state.set_criterion("micro_location", "beira-mar", status="confirmed")
    # Faltando: payment_type e condo_max (dealbreakers para compra com budget alto)

    quality = compute_quality_score(state)

    # Primeira tentativa: deve sugerir um dos dealbreakers
    next_key = next_question_from_quality_gaps(state, quality)
    assert next_key in {"payment_type", "condo_max"}

    # Marcar primeiro como recusado
    first_key = next_key
    mark_field_refusal(state, first_key)
    state.asked_questions.append(first_key)

    # Segunda tentativa: deve sugerir o OUTRO dealbreaker, não o primeiro
    next_key_2 = next_question_from_quality_gaps(state, quality)
    assert next_key_2 != first_key
    assert next_key_2 in {"payment_type", "condo_max", None}

    # Se retornou outro campo, marcar como recusado também
    if next_key_2:
        mark_field_refusal(state, next_key_2)
        state.asked_questions.append(next_key_2)

        # Terceira tentativa: não deve sugerir nenhum dos dois recusados
        next_key_3 = next_question_from_quality_gaps(state, quality)
        assert next_key_3 not in {first_key, next_key_2}


def test_detect_field_refusal():
    """
    Testa detecção de mensagens de recusa.
    """
    # Casos positivos (recusa)
    assert detect_field_refusal("não sei") is True
    assert detect_field_refusal("Não tenho certeza") is True
    assert detect_field_refusal("prefiro não informar") is True
    assert detect_field_refusal("tanto faz") is True
    assert detect_field_refusal("qualquer um") is True
    assert detect_field_refusal("depois eu digo") is True

    # Casos negativos (não é recusa)
    assert detect_field_refusal("2 vagas") is False
    assert detect_field_refusal("Manaíra") is False
    assert detect_field_refusal("até 500 mil") is False


def test_identify_quality_gaps():
    """
    Testa identificação de gaps específicos.
    """
    state = SessionState(session_id="test-5")
    state.intent = "comprar"
    state.set_criterion("city", "João Pessoa", status="inferred")
    state.set_criterion("neighborhood", "Tambaú", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="confirmed")
    state.set_criterion("bedrooms", 2, status="confirmed")
    state.set_criterion("parking", 1, status="confirmed")
    state.set_criterion("budget", 1200000, status="confirmed")  # alto -> precisa condo_max
    state.set_criterion("timeline", "3m", status="confirmed")
    # Faltando: payment_type (compra), condo_max (budget alto), micro_location

    quality = compute_quality_score(state)
    gaps = identify_quality_gaps(state, quality)

    # Deve identificar missing payment_type e condo_max
    assert "payment_type" in gaps.missing_required_fields
    assert "condo_max" in gaps.missing_required_fields

    # Deve identificar city como low confidence (inferred)
    assert "city" in gaps.low_confidence_fields

    # Dealbreakers devem incluir payment_type e condo_max
    assert "payment_type" in gaps.dealbreakers
    assert "condo_max" in gaps.dealbreakers


def test_quality_gate_integration_with_missing_dealbreaker():
    """
    Teste de integração: quality gate identifica dealbreakers missing.
    """
    state = SessionState(session_id="test-6")
    state.intent = "comprar"
    state.set_criterion("city", "João Pessoa", status="inferred")  # inferred reduz score
    state.set_criterion("neighborhood", "Manaíra", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="inferred")  # inferred reduz score
    state.set_criterion("bedrooms", 3, status="confirmed")
    state.set_criterion("parking", 2, status="inferred")  # inferred reduz score
    state.set_criterion("budget", 900000, status="confirmed")
    state.set_criterion("timeline", "flexivel", status="confirmed")  # não dá bônus
    # Faltando: payment_type (dealbreaker para compra), condo_max (budget alto)

    quality = compute_quality_score(state)
    gaps = identify_quality_gaps(state, quality)

    # Deve identificar dealbreakers faltando
    assert "payment_type" in gaps.dealbreakers or "payment_type" in gaps.missing_required_fields
    assert "condo_max" in gaps.dealbreakers or "condo_max" in gaps.missing_required_fields

    # Deve retornar um dos dealbreakers como próxima pergunta
    next_key = next_question_from_quality_gaps(state, quality)
    assert next_key in {"payment_type", "condo_max"}


def test_quality_gate_allows_handoff_when_no_gaps():
    """
    Quality gate deve permitir handoff se não há gaps relevantes, mesmo com grade C.
    """
    state = SessionState(session_id="test-7")
    state.intent = "alugar"
    state.set_criterion("city", "João Pessoa", status="confirmed")
    state.set_criterion("neighborhood", "Tambaú", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="confirmed")
    state.set_criterion("bedrooms", 2, status="confirmed")
    state.set_criterion("parking", 1, status="confirmed")
    state.set_criterion("budget", 3000, status="confirmed")
    state.set_criterion("timeline", "flexivel", status="confirmed")  # flexivel reduz score
    state.lead_profile["name"] = "Maria"

    quality = compute_quality_score(state)

    # Pode ter grade C por timeline flexível, mas não há campos críticos missing
    # Should handoff deve permitir
    result = should_handoff(state, quality)
    assert result is True or quality["grade"] in {"A", "B"}


def test_quality_gate_with_ambiguous_micro_location():
    """
    Quality gate deve detectar micro_location ambígua (orla/inferred) como gap.
    """
    state = SessionState(session_id="test-8")
    state.intent = "alugar"
    state.set_criterion("city", "João Pessoa", status="inferred")  # inferred
    state.set_criterion("neighborhood", "Cabo Branco", status="confirmed")
    state.set_criterion("property_type", "apartamento", status="inferred")  # inferred
    state.set_criterion("bedrooms", 2, status="inferred")  # inferred
    state.set_criterion("parking", 1, status="confirmed")
    state.set_criterion("budget", 4000, status="confirmed")
    state.set_criterion("timeline", "flexivel", status="confirmed")
    state.set_criterion("micro_location", "orla", status="inferred")  # ambíguo!

    quality = compute_quality_score(state)
    gaps = identify_quality_gaps(state, quality)

    # Deve identificar micro_location como ambíguo e dealbreaker
    assert "micro_location" in gaps.ambiguous_fields
    assert "micro_location" in gaps.dealbreakers

    # Deve identificar campos com baixa confiança (inferred)
    assert len(gaps.low_confidence_fields) > 0

    # Deve sugerir micro_location como próxima pergunta (dealbreaker tem prioridade)
    next_key = next_question_from_quality_gaps(state, quality)
    assert next_key == "micro_location"
