from __future__ import annotations
from typing import Dict
from .state import SessionState


def compute_lead_score(state: SessionState) -> Dict[str, object]:
    score = 0
    reasons = []

    if state.criteria.budget:
        score += 20
        reasons.append("budget_defined")
    if state.criteria.city:
        score += 10
        reasons.append("city_defined")
    if state.criteria.neighborhood:
        score += 15
        reasons.append("neighborhood_defined")

    # Micro-location (proximidade da praia) - indica preferência clara
    micro_loc = state.criteria.micro_location
    if micro_loc and str(micro_loc).lower() not in {"orla", "indifferent", "indiferente"}:
        score += 10
        reasons.append("micro_location_defined")
        # Beira-mar indica alto padrão
        if micro_loc == "beira-mar":
            score += 5
            reasons.append("beachfront_preference")

    if state.criteria.bedrooms and state.criteria.bedrooms >= 3:
        score += 10
        reasons.append("3_plus_bedrooms")

    # Suítes - indica imóvel de padrão mais alto
    if state.criteria.suites and state.criteria.suites >= 1:
        score += 8
        reasons.append("suites_preference")
        if state.criteria.suites >= 2:
            score += 5
            reasons.append("multiple_suites")

    # Banheiros - múltiplos banheiros indicam imóvel maior
    bathrooms = state.criteria.bathrooms_min
    if bathrooms and bathrooms >= 2:
        score += 5
        reasons.append("multiple_bathrooms")

    if state.criteria.parking and state.criteria.parking >= 2:
        score += 5
        reasons.append("2_plus_parking")

    # Leisure - área de lazer completa indica alto padrão
    leisure_req = state.triage_fields.get("leisure_required", {}).get("value")
    leisure_level = state.triage_fields.get("leisure_level", {}).get("value")
    if leisure_req == "yes":
        score += 3
        reasons.append("leisure_required")
        if leisure_level == "full":
            score += 5
            reasons.append("leisure_full_preference")

    if state.intent in {"comprar", "alugar"}:
        score += 5
        reasons.append("intent_confirmed")

    tl = state.criteria.timeline
    if tl == "30d":
        score += 25
        reasons.append("timeline_30d")
    elif tl == "3m":
        score += 20
        reasons.append("timeline_3m")
    elif tl == "6m":
        score += 10
        reasons.append("timeline_6m")
    elif tl == "12m":
        score += 5
        reasons.append("timeline_12m")

    # Intent stage (engajamento)
    intent_stage = getattr(state, "intent_stage", "unknown")
    if intent_stage == "ready_to_visit":
        score += 8
        reasons.append("intent_stage_ready_to_visit")
    elif intent_stage == "negotiating":
        score += 8
        reasons.append("intent_stage_negotiating")
    elif intent_stage == "researching":
        if tl not in {"30d", "3m"}:
            score -= 5
        reasons.append("intent_stage_researching")

    score = max(0, score)
    score = min(score, 100)

    if score >= 70:
        temperature = "hot"
    elif score >= 40:
        temperature = "warm"
    else:
        temperature = "cold"

    return {"temperature": temperature, "score": score, "reasons": reasons}
