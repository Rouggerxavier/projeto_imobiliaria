"""
Quality Gate - Controle de Handoff Baseado em Quality Score

Previne handoff prematuro quando quality_score é baixo (C/D).
Identifica gaps específicos e gera perguntas cirúrgicas para melhorar a qualidade.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from .state import SessionState
from .rules import CRITICAL_ORDER

# === CONFIGURAÇÕES DO QUALITY GATE ===

# Máximo de perguntas de quality gate antes de permitir handoff mesmo com score baixo
MAX_QUALITY_GATE_TURNS = 3

# Grade mínima para permitir handoff sem perguntas extras (A ou B)
QUALITY_GATE_MIN_GRADE = "B"

# Threshold de score mínimo para bypass do gate (equivalente a B = 70)
QUALITY_GATE_MIN_SCORE = 70


@dataclass
class QualityGaps:
    """Estrutura que identifica gaps específicos no quality score."""
    missing_required_fields: List[str]
    ambiguous_fields: List[str]
    conflicting_fields: List[str]
    low_confidence_fields: List[str]
    dealbreakers: List[str]


def should_handoff(state: SessionState, quality: Dict[str, Any]) -> bool:
    """
    Decide se deve permitir handoff baseado no quality_score e estado atual.

    Args:
        state: Estado da sessão
        quality: Resultado de compute_quality_score(state)

    Returns:
        True se pode fazer handoff, False se precisa de mais perguntas
    """
    grade = quality.get("grade", "D")
    score = quality.get("score", 0)

    # 1. Se atingiu limite de perguntas de gate, permitir handoff mesmo com score baixo
    if state.quality_gate_turns >= MAX_QUALITY_GATE_TURNS:
        print(f"[QUALITY_GATE] Handoff permitido: limite de {MAX_QUALITY_GATE_TURNS} perguntas atingido")
        return True

    # 2. Se quality_score é A ou B, permitir handoff
    if grade in {"A", "B"} or score >= QUALITY_GATE_MIN_SCORE:
        print(f"[QUALITY_GATE] Handoff permitido: grade={grade}, score={score}")
        return True

    # 3. Se score é C ou D, verificar se há gaps que podem ser preenchidos
    gaps = identify_quality_gaps(state, quality)

    # Se não há campos missing/ambiguous/conflicting relevantes, permitir handoff
    total_gaps = len(gaps.missing_required_fields) + len(gaps.ambiguous_fields) + len(gaps.conflicting_fields)
    if total_gaps == 0:
        print(f"[QUALITY_GATE] Handoff permitido: sem gaps relevantes (grade={grade})")
        return True

    # 4. Se há gaps e ainda não atingiu limite, bloquear handoff
    print(f"[QUALITY_GATE] Handoff bloqueado: grade={grade}, score={score}, gaps={total_gaps}, turns={state.quality_gate_turns}/{MAX_QUALITY_GATE_TURNS}")
    return False


def identify_quality_gaps(state: SessionState, quality: Dict[str, Any]) -> QualityGaps:
    """
    Identifica gaps específicos a partir dos motivos do quality_score.

    Args:
        state: Estado da sessão
        quality: Resultado de compute_quality_score(state)

    Returns:
        QualityGaps com listas de campos específicos
    """
    reasons = quality.get("reasons", [])

    missing_required_fields: List[str] = []
    ambiguous_fields: List[str] = []
    conflicting_fields: List[str] = []
    low_confidence_fields: List[str] = []
    dealbreakers: List[str] = []

    for reason in reasons:
        # Missing critical fields
        if reason.startswith("missing_critical_"):
            field = reason.replace("missing_critical_", "")
            if field not in missing_required_fields:
                missing_required_fields.append(field)

        # Inferred fields (baixa confiança)
        elif reason.startswith("inferred_"):
            field = reason.replace("inferred_", "")
            if field not in low_confidence_fields:
                low_confidence_fields.append(field)

        # Dealbreakers
        elif reason == "micro_location_ambiguous":
            if "micro_location" not in ambiguous_fields:
                ambiguous_fields.append("micro_location")
            if "micro_location" not in dealbreakers:
                dealbreakers.append("micro_location")

        elif reason == "missing_condo_max_high_budget":
            if "condo_max" not in missing_required_fields:
                missing_required_fields.append("condo_max")
            if "condo_max" not in dealbreakers:
                dealbreakers.append("condo_max")

        elif reason == "missing_payment_type":
            if "payment_type" not in missing_required_fields:
                missing_required_fields.append("payment_type")
            if "payment_type" not in dealbreakers:
                dealbreakers.append("payment_type")

        # Conflitos
        elif reason == "unresolved_conflict":
            # Não temos campo específico, mas isso indica problema
            pass

        # Inconsistências
        elif reason == "neighborhood_without_city":
            if "city" not in conflicting_fields:
                conflicting_fields.append("city")

        elif reason == "budget_inconsistent":
            if "budget" not in conflicting_fields:
                conflicting_fields.append("budget")

    return QualityGaps(
        missing_required_fields=missing_required_fields,
        ambiguous_fields=ambiguous_fields,
        conflicting_fields=conflicting_fields,
        low_confidence_fields=low_confidence_fields,
        dealbreakers=dealbreakers
    )


def next_question_from_quality_gaps(state: SessionState, quality: Dict[str, Any]) -> Optional[str]:
    """
    Escolhe a próxima pergunta cirúrgica baseada nos gaps identificados.

    Prioridade:
    1. Campos críticos faltando (dealbreakers primeiro)
    2. Campos ambíguos
    3. Campos com baixa confiança (inferred)
    4. Conflitos

    Args:
        state: Estado da sessão
        quality: Resultado de compute_quality_score(state)

    Returns:
        question_key para usar em choose_question(), ou None se não há gaps
    """
    gaps = identify_quality_gaps(state, quality)

    # Prioridade 1: Dealbreakers (campos críticos que bloqueiam qualidade)
    for field in gaps.dealbreakers:
        # Não perguntar se já foi recusado explicitamente
        if state.field_refusals.get(field, 0) > 0:
            continue
        # Não perguntar se já perguntou muito recentemente (últimas 2 perguntas)
        if field == state.last_question_key:
            continue
        # Perguntar se não foi perguntado ainda ou foi há muito tempo
        if field not in state.asked_questions or state.asked_questions.count(field) == 0:
            return field

    # Prioridade 2: Campos críticos missing (seguindo CRITICAL_ORDER)
    for field in CRITICAL_ORDER:
        if field in gaps.missing_required_fields:
            if state.field_refusals.get(field, 0) > 0:
                continue
            if field == state.last_question_key:
                continue
            if field not in state.asked_questions:
                return field

    # Prioridade 3: Outros missing não críticos
    for field in gaps.missing_required_fields:
        if field not in CRITICAL_ORDER:
            if state.field_refusals.get(field, 0) > 0:
                continue
            if field == state.last_question_key:
                continue
            if field not in state.asked_questions:
                return field

    # Prioridade 4: Campos ambíguos (ex: micro_location "orla")
    for field in gaps.ambiguous_fields:
        if state.field_refusals.get(field, 0) > 0:
            continue
        if field == state.last_question_key:
            continue
        # Permitir re-perguntar ambiguous mesmo se já foi perguntado uma vez
        if state.asked_questions.count(field) < 2:
            return field

    # Prioridade 5: Campos com baixa confiança (inferred)
    for field in gaps.low_confidence_fields:
        if state.field_refusals.get(field, 0) > 0:
            continue
        if field == state.last_question_key:
            continue
        # Confirmar campos inferred que ainda não foram confirmados
        if field == "city":
            return "city_confirm"
        if state.asked_questions.count(field) < 2:
            return field

    # Prioridade 6: Conflitos (tentar resolver)
    for field in gaps.conflicting_fields:
        if state.field_refusals.get(field, 0) > 0:
            continue
        if field == state.last_question_key:
            continue
        if state.asked_questions.count(field) < 2:
            return field

    # Sem gaps para endereçar
    return None


def mark_field_refusal(state: SessionState, field: str) -> None:
    """
    Marca que o usuário recusou informar um campo específico.

    Isso evita que o sistema fique perguntando repetidamente o mesmo campo.

    Args:
        state: Estado da sessão
        field: Nome do campo recusado
    """
    current_count = state.field_refusals.get(field, 0)
    state.field_refusals[field] = current_count + 1
    print(f"[QUALITY_GATE] Campo '{field}' marcado como recusado (count={state.field_refusals[field]})")


def detect_field_refusal(message: str) -> bool:
    """
    Detecta se a mensagem indica recusa em fornecer informação.

    Args:
        message: Mensagem do usuário

    Returns:
        True se a mensagem indica recusa
    """
    message_lower = message.lower().strip()

    refusal_patterns = [
        "não sei",
        "nao sei",
        "não tenho certeza",
        "nao tenho certeza",
        "não informo",
        "nao informo",
        "prefiro não",
        "prefiro nao",
        "não quero",
        "nao quero",
        "pular",
        "próxima",
        "proxima",
        "não importa",
        "nao importa",
        "tanto faz",
        "qualquer",
        "depois",
        "ainda não",
        "ainda nao",
    ]

    return any(pattern in message_lower for pattern in refusal_patterns)
