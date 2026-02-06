"""
SLA Policy - Service Level Agreements e Fluxo Diferenciado por Lead Score

Classifica leads em HOT/WARM/COLD e define ações automáticas:
- HOT: resposta imediata, roteamento prioritário, evento HOT_LEAD
- WARM: handoff normal
- COLD: handoff normal ou nutrição
"""

from __future__ import annotations
import os
from typing import Dict, Any, Literal, Tuple, Optional
from .state import SessionState

# === CONFIGURAÇÕES DE THRESHOLDS ===

# Thresholds de lead_score para classificação (0-100)
HOT_THRESHOLD = int(os.getenv("SLA_HOT_THRESHOLD", "80"))      # >= 80 = HOT
WARM_THRESHOLD = int(os.getenv("SLA_WARM_THRESHOLD", "50"))    # 50-79 = WARM
# < 50 = COLD

LeadClass = Literal["HOT", "WARM", "COLD"]
SLAType = Literal["immediate", "normal", "nurture"]


def classify_lead(lead_score: int | float, session_state: SessionState) -> LeadClass:
    """
    Classifica lead em HOT/WARM/COLD baseado no lead_score.

    Args:
        lead_score: Pontuação do lead (0-100)
        session_state: Estado da sessão (para contexto adicional se necessário)

    Returns:
        "HOT", "WARM" ou "COLD"
    """
    score = int(lead_score)

    if score >= HOT_THRESHOLD:
        return "HOT"
    elif score >= WARM_THRESHOLD:
        return "WARM"
    else:
        return "COLD"


def compute_sla_action(
    lead_class: LeadClass,
    quality_grade: str,
    session_state: SessionState
) -> Dict[str, Any]:
    """
    Calcula ação SLA baseada na classificação do lead.

    Args:
        lead_class: Classificação HOT/WARM/COLD
        quality_grade: Grade de qualidade (A/B/C/D)
        session_state: Estado da sessão

    Returns:
        {
            "sla_type": "immediate" | "normal" | "nurture",
            "priority": bool,
            "should_emit_hot_event": bool,
            "message_template": str,
            "routing_strategy": "priority" | "normal" | "delayed"
        }
    """
    if lead_class == "HOT":
        return {
            "sla_type": "immediate",
            "priority": True,
            "should_emit_hot_event": not session_state.hot_lead_emitted,
            "message_template": "hot",
            "routing_strategy": "priority"
        }

    elif lead_class == "WARM":
        return {
            "sla_type": "normal",
            "priority": False,
            "should_emit_hot_event": False,
            "message_template": "warm",
            "routing_strategy": "normal"
        }

    else:  # COLD
        # COLD com qualidade boa: handoff normal
        # COLD com qualidade baixa: nutrição
        if quality_grade in {"A", "B"}:
            return {
                "sla_type": "normal",
                "priority": False,
                "should_emit_hot_event": False,
                "message_template": "cold_handoff",
                "routing_strategy": "normal"
            }
        else:
            return {
                "sla_type": "nurture",
                "priority": False,
                "should_emit_hot_event": False,
                "message_template": "cold_nurture",
                "routing_strategy": "delayed"
            }


def get_sla_message(
    message_template: str,
    agent_name: Optional[str] = None,
    expose_contact: bool = False,
    agent_whatsapp: Optional[str] = None
) -> str:
    """
    Retorna mensagem final ao cliente baseada no template SLA.

    Args:
        message_template: Template ("hot", "warm", "cold_handoff", "cold_nurture")
        agent_name: Nome do corretor atribuído
        expose_contact: Se deve expor contato do corretor
        agent_whatsapp: WhatsApp do corretor

    Returns:
        Mensagem formatada em PT-BR
    """
    if message_template == "hot":
        if agent_name:
            base = f"Perfeito! Já acionei {agent_name} agora e ele deve te chamar em instantes."
        else:
            base = "Perfeito! Já acionei um corretor agora e ele deve te chamar em instantes."

        if expose_contact and agent_whatsapp:
            base += f" Contato: {agent_whatsapp}"

        return base

    elif message_template == "warm":
        if agent_name:
            return f"Entendi seu perfil! Vou repassar para {agent_name}, que vai entrar em contato em breve."
        else:
            return "Entendi seu perfil! Um corretor vai entrar em contato em breve para te ajudar."

    elif message_template == "cold_handoff":
        return "Anotei suas preferências. Um corretor vai avaliar as opções e entrar em contato."

    elif message_template == "cold_nurture":
        return "Anotei suas preferências. Vou te manter informado sobre opções que se encaixem no seu perfil."

    else:
        # Fallback
        return "Entendi seu perfil! Um corretor vai entrar em contato em breve."


def should_emit_hot_event(session_state: SessionState, lead_class: LeadClass) -> bool:
    """
    Verifica se deve emitir evento HOT_LEAD.

    Proteção contra emissão duplicada: só emite uma vez por sessão.

    Args:
        session_state: Estado da sessão
        lead_class: Classificação do lead

    Returns:
        True se deve emitir, False caso contrário
    """
    if lead_class != "HOT":
        return False

    if session_state.hot_lead_emitted:
        print(f"[SLA] HOT_LEAD já emitido para session_id={session_state.session_id}, ignorando duplicata")
        return False

    return True


def build_hot_lead_event(
    lead_id: str,
    session_state: SessionState,
    lead_score: int,
    quality_grade: str,
    assigned_agent: Optional[Dict[str, Any]] = None,
    timestamp: float = None
) -> Dict[str, Any]:
    """
    Constrói payload completo do evento HOT_LEAD.

    Args:
        lead_id: ID único do lead
        session_state: Estado da sessão
        lead_score: Pontuação final do lead
        quality_grade: Grade de qualidade (A/B/C/D)
        assigned_agent: Info do corretor atribuído (opcional)
        timestamp: Timestamp do evento (opcional, usa current time se None)

    Returns:
        Dicionário com evento estruturado
    """
    import time

    event = {
        "type": "HOT_LEAD",
        "lead_id": lead_id,
        "session_id": session_state.session_id,
        "timestamp": timestamp or time.time(),
        "lead_score": lead_score,
        "lead_class": "HOT",
        "quality_grade": quality_grade,
        "sla": "immediate",

        # Perfil do lead
        "lead_profile": {
            "name": session_state.lead_profile.get("name"),
            "phone": session_state.lead_profile.get("phone"),
            "email": session_state.lead_profile.get("email"),
        },

        # Critérios principais
        "criteria": {
            "intent": session_state.intent,
            "city": session_state.criteria.city,
            "neighborhood": session_state.criteria.neighborhood,
            "micro_location": session_state.criteria.micro_location,
            "property_type": session_state.criteria.property_type,
            "bedrooms": session_state.criteria.bedrooms,
            "parking": session_state.criteria.parking,
            "budget": session_state.criteria.budget,
            "timeline": session_state.criteria.timeline,
        },

        # Agente atribuído
        "assigned_agent": assigned_agent or {"queue": "priority"},
    }

    return event


def get_thresholds_info() -> Dict[str, int]:
    """
    Retorna thresholds configurados para documentação/debug.

    Returns:
        Dicionário com HOT_THRESHOLD, WARM_THRESHOLD
    """
    return {
        "HOT_THRESHOLD": HOT_THRESHOLD,
        "WARM_THRESHOLD": WARM_THRESHOLD,
        "COLD_RANGE": f"< {WARM_THRESHOLD}"
    }
