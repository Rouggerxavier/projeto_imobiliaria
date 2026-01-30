from __future__ import annotations
import os
from typing import Dict, List, Optional
from .state import SessionState

TRIAGE_ONLY = os.getenv("TRIAGE_ONLY", "false").strip().lower() in ("true", "1", "yes", "on")


def has_location(state: SessionState) -> bool:
    return bool(state.criteria.neighborhood or state.criteria.city)


def has_budget(state: SessionState) -> bool:
    return state.criteria.budget is not None and state.criteria.budget > 0


def has_type(state: SessionState) -> bool:
    return state.criteria.property_type is not None


def can_search_properties(state: SessionState) -> bool:
    if TRIAGE_ONLY:
        return False
    if state.intent not in {"comprar", "alugar", "investir"}:
        return False
    if not has_location(state):
        return False
    if not has_budget(state):
        return False
    if not has_type(state):
        return False
    return True


def can_answer_about_property(data: Optional[Dict]) -> bool:
    return bool(data and data.get("id"))


def missing_critical_fields(state: SessionState) -> List[str]:
    # Fluxo padrão (não triagem): mesma lógica anterior
    if not TRIAGE_ONLY:
        missing: List[str] = []
        if not has_location(state):
            missing.append("location")
        if not has_budget(state):
            missing.append("budget")
        if not has_type(state):
            missing.append("property_type")
        return missing

    # Ordem de priorização para triagem completa
    order = [
        "intent",
        "city",
        "neighborhood",
        "property_type",
        "bedrooms",
        "parking",
        "budget",
        "timeline",
    ]

    def _filled(key: str) -> bool:
        if key == "intent" and state.intent:
            return True
        # Se já está em triage_fields (mesmo None, mas confirmado/inferido), considere preenchido
        if key in state.triage_fields:
            return True
        # Campos críticos refletem em criteria + status
        if hasattr(state.criteria, key) and state.get_criterion(key) is not None:
            return True
        # Se bairro/cidade mapeiam para location
        if key == "city" and state.criteria.city:
            return True
        if key == "neighborhood" and state.criteria.neighborhood:
            return True
        return False

    missing: List[str] = [k for k in order if not _filled(k)]
    return missing


QUESTION_BANK: Dict[str, str] = {
    "intent": "Você quer comprar ou alugar?",
    "city": "Qual cidade você prefere? (João Pessoa como padrão, se for o caso)",
    "neighborhood": "Algum bairro preferido? Se não souber, posso seguir sem isso.",
    "property_type": "Prefere apartamento, casa, cobertura ou outro tipo?",
    "bedrooms": "Quantos quartos você precisa? Quer suíte?",
    "parking": "Quantas vagas de garagem você precisa (1, 2, 3)?",
    "budget": "Qual o orçamento máximo? Pode ser aproximado.",
    "timeline": "Qual o prazo para mudar/fechar? (ex.: imediato, até 6 meses)",
}


def next_best_question(state: SessionState) -> Optional[str]:
    missing = missing_critical_fields(state)
    if not missing:
        return None
    for key in missing:
        if key not in state.asked_questions:
            return QUESTION_BANK.get(key)
    return QUESTION_BANK.get(missing[0])
