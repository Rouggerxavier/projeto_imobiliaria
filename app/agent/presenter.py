"""
Presentation Layer - Formatação de Respostas para o Usuário

Este módulo encapsula toda a lógica de formatação e apresentação,
separando as responsabilidades de apresentação da lógica de negócio.
"""

from __future__ import annotations
import os
from typing import Dict, Any, List
from .state import SessionState


CRITICAL_ORDER = [
    "intent",
    "city",
    "neighborhood",
    "micro_location",
    "property_type",
    "bedrooms",
    "suites",
    "parking",
    "budget",
    "budget_min",
    "timeline",
]


def format_price(intent: str, prop: Dict[str, Any]) -> str:
    """
    Formata o preço de um imóvel de acordo com a intenção (alugar/comprar).

    Args:
        intent: "alugar" ou "comprar"
        prop: Dicionário com dados do imóvel

    Returns:
        String formatada do preço (ex: "R$3.500/mes" ou "R$450.000")
    """
    if intent == "alugar":
        price = prop.get("preco_aluguel")
        if price:
            return f"R${price:,.0f}/mes".replace(",", ".")
    else:
        price = prop.get("preco_venda")
        if price:
            return f"R${price:,.0f}".replace(",", ".")
    return "Consulte"


def format_option(idx: int, intent: str, prop: Dict[str, Any]) -> str:
    """
    Formata uma opção de imóvel para apresentação ao usuário.

    Args:
        idx: Índice da opção (1, 2, 3...)
        intent: "alugar" ou "comprar"
        prop: Dicionário com dados do imóvel

    Returns:
        String formatada com todas as informações do imóvel
    """
    price_txt = format_price(intent, prop)
    return (
        f"{idx}) {prop.get('titulo')} - {prop.get('bairro')}/{prop.get('cidade')}\n"
        f"   {prop.get('quartos')}q • {prop.get('vagas')} vaga(s) • {prop.get('area_m2')} m²\n"
        f"   {price_txt} • {prop.get('descricao_curta')}"
    )


def format_property_list(properties: List[Dict[str, Any]], intent: str) -> str:
    """
    Formata uma lista de imóveis para apresentação.

    Args:
        properties: Lista de imóveis
        intent: "alugar" ou "comprar"

    Returns:
        String com todos os imóveis formatados
    """
    lines: List[str] = []
    for idx, prop in enumerate(properties, start=1):
        lines.append(format_option(idx, intent, prop))

    prefix = "Encontrei estas opções:" if len(lines) > 1 else "Achei esta opção:"
    footer = "Quer agendar visita ou refinar (bairro/quartos/orçamento)?"

    return prefix + "\n" + "\n".join(lines) + "\n" + footer


def build_summary_payload(state: SessionState, assigned_agent: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Gera resumo estruturado para handoff/CRM.

    Args:
        state: Estado da sessão
        assigned_agent: Informações do corretor atribuído (opcional)

    Returns:
        Dicionário com texto formatado e payload estruturado
    """
    critical = {}
    for field in CRITICAL_ORDER:
        if field == "intent":
            critical[field] = state.intent
        elif hasattr(state.criteria, field):
            critical[field] = getattr(state.criteria, field)
        else:
            critical[field] = state.triage_fields.get(field, {}).get("value")

    preferences = {k: v.get("value") for k, v in state.triage_fields.items() if k not in CRITICAL_ORDER}

    summary_json = {
        "session_id": state.session_id,
        "lead_profile": state.lead_profile,
        "critical": critical,
        "preferences": preferences,
        "lead_score": state.lead_score.__dict__,
        "status": "triage_completed",
        "intent_stage": state.intent_stage,
    }

    # Texto curto para humano (bullets)
    txt_parts = []
    if critical.get("intent"):
        txt_parts.append(f"Operação: {critical['intent']}")
    if critical.get("city"):
        txt_parts.append(f"Cidade: {critical['city']}")
    if critical.get("neighborhood") is not None:
        txt_parts.append(f"Bairro: {critical['neighborhood'] or 'sem preferência'}")
    if critical.get("micro_location"):
        txt_parts.append(f"Micro-localização: {critical['micro_location']}")
    if critical.get("property_type"):
        txt_parts.append(f"Tipo: {critical['property_type']}")
    if critical.get("bedrooms"):
        txt_parts.append(f"Quartos: {critical['bedrooms']}")
    if critical.get("suites"):
        txt_parts.append(f"Suítes: {critical['suites']}")
    if critical.get("parking"):
        txt_parts.append(f"Vagas: {critical['parking']}")
    if critical.get("budget"):
        txt_parts.append(f"Orçamento máx.: R$ {critical['budget']}")
    if critical.get("timeline"):
        txt_parts.append(f"Prazo: {critical['timeline']}")
    if state.intent_stage and state.intent_stage != "unknown":
        friendly_stage = {
            "researching": "Fase: pesquisando",
            "ready_to_visit": "Fase: pronto para visitar",
            "negotiating": "Fase: negociando",
        }.get(state.intent_stage, f"Fase: {state.intent_stage}")
        txt_parts.append(friendly_stage)

    # Monta o resumo com os critérios do cliente
    if txt_parts:
        summary_text = "Resumo da triagem:\n- " + "\n- ".join(txt_parts)
        transition = format_handoff_message("final", assigned_agent=assigned_agent)
        summary_text += f"\n\n{transition}"
    else:
        summary_text = format_handoff_message("final", assigned_agent=assigned_agent)

    return {"text": summary_text, "payload": summary_json}


def format_handoff_message(reason: str, assigned_agent: Dict[str, Any] | None = None) -> str:
    """
    Retorna a mensagem apropriada para cada tipo de handoff.

    Args:
        reason: Motivo do handoff (pedido_humano, negociacao, visita, etc.)
        assigned_agent: opcional, dados do corretor já atribuído

    Returns:
        Mensagem formatada para o usuário
    """
    expose_contact = os.getenv("EXPOSE_AGENT_CONTACT", "false").lower() in ("true", "1", "yes")
    agent_name = assigned_agent.get("name") if assigned_agent else None

    if reason == "final":
        if expose_contact and agent_name:
            return (
                f"Perfeito, obrigado! Vou repassar essas informações para o(a) corretor(a) {agent_name}, "
                "que vai entrar em contato por aqui para te enviar opções dentro do seu perfil."
            )
        return (
            "Perfeito, obrigado! Vou repassar essas informações para um corretor, "
            "que vai entrar em contato por aqui para te enviar opções dentro do seu perfil."
        )

    replies = {
        "pedido_humano": "Tudo bem, vou te passar para um corretor agora.",
        "negociacao": "Vou acionar um corretor para tratar do valor e te responder rapidinho.",
        "visita": "Vou chamar um corretor para agendar a visita. Qual horário funciona melhor?",
        "reclamacao": "Sinto muito pela experiência. Vou passar para um corretor resolver agora.",
        "juridico": "Posso pedir para um corretor te ajudar com essa parte contratual. Pode ser?",
        "alta_intencao": "Vejo que você quer fechar rápido. Posso acionar um corretor para agilizar?",
    }
    return replies.get(reason, "Vou acionar um corretor humano para te ajudar melhor.")
