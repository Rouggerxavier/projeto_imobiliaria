"""
Quality Score - Avaliação de Completude e Confiança do Lead

Calcula um score de qualidade baseado em:
- Completude dos campos críticos
- Proporção de campos confirmed vs inferred
- Presença de dealbreakers não resolvidos
- Consistência (ausência de conflitos)

Objetivo: Identificar leads que precisam de follow-up antes do handoff.
"""

from __future__ import annotations
from typing import Dict, Any, List
from .state import SessionState
from .rules import CRITICAL_ORDER


def compute_quality_score(state: SessionState) -> Dict[str, Any]:
    """
    Calcula score de qualidade do lead (0-100) e grade (A/B/C/D).

    Args:
        state: Estado da sessão

    Returns:
        {
            "score": int (0-100),
            "grade": str ("A"|"B"|"C"|"D"),
            "reasons": List[str],
            "completeness": float (0.0-1.0),
            "confidence": float (0.0-1.0)
        }
    """
    score = 100
    reasons = []

    # === COMPLETUDE DOS CAMPOS CRÍTICOS ===
    critical_fields = CRITICAL_ORDER  # ["intent", "city", "neighborhood", "property_type", "bedrooms", "parking", "budget", "timeline"]
    total_critical = len(critical_fields)
    filled_critical = 0
    confirmed_critical = 0

    for field in critical_fields:
        if field == "intent":
            if state.intent:
                filled_critical += 1
                confirmed_critical += 1
            else:
                score -= 15
                reasons.append(f"missing_critical_{field}")
        else:
            field_data = state.triage_fields.get(field)
            if field_data and field_data.get("value") is not None:
                filled_critical += 1
                if field_data.get("status") == "confirmed":
                    confirmed_critical += 1
                elif field_data.get("status") == "inferred":
                    score -= 5
                    reasons.append(f"inferred_{field}")
            else:
                # Campo crítico faltando
                score -= 15
                reasons.append(f"missing_critical_{field}")

    completeness = filled_critical / total_critical if total_critical > 0 else 0.0
    confidence = confirmed_critical / filled_critical if filled_critical > 0 else 0.0

    # === DEALBREAKERS NÃO RESOLVIDOS ===

    # Micro-location "orla" sem confirmação específica
    micro_loc = state.triage_fields.get("micro_location")
    if micro_loc:
        micro_val = micro_loc.get("value")
        micro_status = micro_loc.get("status")
        if micro_val == "orla" or micro_status == "inferred":
            score -= 10
            reasons.append("micro_location_ambiguous")

    # Condomínio máximo ausente para budget alto
    budget = state.criteria.budget
    condo_max = state.criteria.condo_max
    if budget and budget > 500000 and not condo_max:
        score -= 8
        reasons.append("missing_condo_max_high_budget")

    # Forma de pagamento ausente para compra
    if state.intent == "comprar":
        payment_type = state.triage_fields.get("payment_type")
        if not payment_type or not payment_type.get("value"):
            score -= 5
            reasons.append("missing_payment_type")

    # === CONFLITOS PENDENTES ===
    # Verifica se há conflitos no histórico recente (últimas 3 mensagens)
    recent_history = state.history[-3:] if len(state.history) >= 3 else state.history
    for entry in recent_history:
        text = entry.get("text", "").lower()
        if "duas respostas diferentes" in text or "qual vale" in text:
            score -= 20
            reasons.append("unresolved_conflict")
            break

    # === CONSISTÊNCIA DE DADOS ===

    # Bairro sem cidade
    if state.criteria.neighborhood and not state.criteria.city:
        score -= 10
        reasons.append("neighborhood_without_city")

    # Budget_min > Budget_max
    if state.criteria.budget_min and state.criteria.budget:
        if state.criteria.budget_min > state.criteria.budget:
            score -= 15
            reasons.append("budget_inconsistent")

    # Timeline ausente mas urgency definida
    timeline = state.criteria.timeline
    if not timeline and state.criteria.urgency:
        score -= 5
        reasons.append("timeline_missing_with_urgency")

    # === BÔNUS POR CAMPOS EXTRAS ===

    # Micro-location confirmada e específica
    if micro_loc and micro_loc.get("status") == "confirmed" and micro_val not in ["orla", None]:
        score += 5
        reasons.append("micro_location_confirmed")

    # Suites definidas
    if state.criteria.suites and state.criteria.suites > 0:
        score += 3
        reasons.append("suites_defined")

    # Nome do lead disponível
    if state.lead_profile.get("name"):
        score += 2
        reasons.append("name_available")

    # Timeline bem definida (não "flexível")
    if timeline and timeline != "flexivel":
        score += 3
        reasons.append("timeline_specific")

    # === LIMITES ===
    score = max(0, min(100, score))

    # === GRADE ===
    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 50:
        grade = "C"
    else:
        grade = "D"

    return {
        "score": score,
        "grade": grade,
        "reasons": reasons,
        "completeness": round(completeness, 2),
        "confidence": round(confidence, 2)
    }
