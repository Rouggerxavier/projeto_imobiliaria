from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .ai_agent import get_agent
from .state import SessionState


# Enum estrito de ações permitidas
ALLOWED_ACTIONS: Set[str] = {"ASK", "SEARCH", "LIST", "REFINE", "SCHEDULE", "HANDOFF", "ANSWER_GENERAL", "CLARIFY"}

# Campos permitidos em filters
ALLOWED_FILTER_KEYS: Set[str] = {
    "city", "neighborhood", "property_type", "bedrooms", 
    "parking", "budget", "pet", "furnished"
}


@dataclass
class Plan:
    """Representa o plano de ação decidido pelo agente de IA"""
    action: str
    message: str
    question_key: Optional[str] = None
    question: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    handoff_reason: Optional[str] = None
    state_updates: Dict[str, Any] = field(default_factory=dict)
    reasoning: Optional[str] = None  # Para debug/logging


def _validate_and_sanitize_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida e sanitiza filters para evitar campos inválidos.
    
    Returns:
        Dict com apenas campos permitidos e tipos corretos
    """
    if not filters:
        return {}
    
    sanitized = {}
    for key, value in filters.items():
        # Ignora campos não permitidos
        if key not in ALLOWED_FILTER_KEYS:
            print(f"⚠️ Campo inválido ignorado em filters: {key}")
            continue
        
        # Valida tipos básicos
        if value is None:
            continue
        
        try:
            # Validações específicas por campo
            if key in {"bedrooms", "parking"}:
                sanitized[key] = int(value) if value else None
            elif key == "budget":
                sanitized[key] = int(value) if value else None
            elif key in {"pet", "furnished"}:
                sanitized[key] = bool(value) if value is not None else None
            else:
                sanitized[key] = str(value) if value else None
        except (ValueError, TypeError) as e:
            print(f"⚠️ Erro ao validar {key}={value}: {e}")
            continue
    
    return sanitized


def _coerce_plan(raw: Dict[str, Any]) -> Plan:
    """
    Valida e normaliza o plano retornado pela IA.
    Aplica fallbacks seguros se algo estiver inválido.
    """
    action = raw.get("action", "ASK")
    
    # Validação estrita de action
    if action not in ALLOWED_ACTIONS:
        print(f"⚠️ Ação inválida '{action}', usando ASK como fallback")
        action = "ASK"
    
    # Valida e sanitiza filters
    filters = _validate_and_sanitize_filters(raw.get("filters") or {})
    
    # Mensagem segura (nunca vazia)
    message = str(raw.get("message") or raw.get("question") or "")
    if not message.strip():
        message = "Pode me dar mais informações para eu ajudar melhor?"
        print("⚠️ Mensagem vazia retornada pela LLM, usando fallback")
    
    return Plan(
        action=action,
        message=message,
        question_key=raw.get("question_key"),
        question=raw.get("question") or message,
        filters=filters,
        handoff_reason=raw.get("handoff_reason"),
        state_updates=raw.get("state_updates") or {},
        reasoning=raw.get("reasoning")
    )


def plan_next_step(
    message: str,
    state: SessionState,
    extracted: Dict[str, Any],
    missing: List[str],
    search_results: Optional[List[Dict[str, Any]]] = None,
) -> Plan:
    """
    Decide a próxima ação do agente usando IA.
    
    Esta é a função central do fluxo conversacional.
    A IA analisa o contexto completo e decide o que fazer.
    
    Args:
        message: Última mensagem do cliente
        state: Estado completo da sessão
        extracted: Critérios extraídos da mensagem atual
        missing: Lista de campos críticos ainda faltando
        search_results: Resultados de busca de imóveis (se houver)
        
    Returns:
        Plan com a ação decidida e mensagem para o cliente
    """
    agent = get_agent()
    
    # Usa o agente de IA para planejar
    try:
        plan_dict = agent.plan_next_step(
            message=message,
            state=state,
            extracted=extracted,
            missing_fields=missing,
            search_results=search_results
        )
        
        plan = _coerce_plan(plan_dict)
        
        # Log para debug (em produção, use logging apropriado)
        if plan.reasoning:
            print(f"🧠 Plano: {plan.action} - {plan.reasoning}")
        
        return plan
        
    except Exception as e:
        # Em caso de erro, retorna plano seguro de fallback
        print(f"❌ Erro ao planejar próxima ação: {e}")
        return Plan(
            action="ASK",
            message="Desculpe, pode repetir? Quero entender melhor sua necessidade.",
            question_key="clarification",
            reasoning=f"Erro no planejamento: {e}"
        )
