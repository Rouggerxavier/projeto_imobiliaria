"""
Presentation Layer - Formatação de Respostas para o Usuário

Este módulo encapsula toda a lógica de formatação e apresentação,
separando as responsabilidades de apresentação da lógica de negócio.
"""

from __future__ import annotations
import os
import hashlib
from typing import Dict, Any, List, Optional
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


def _fake_phone(session_id: str, agent_name: Optional[str]) -> str:
    """
    Gera um número de WhatsApp fictício, porém estável para a mesma sessão/nome.
    Formato: (83) 9xxxx-xxxx  (DDD de João Pessoa)
    """
    seed_str = f"{session_id}:{agent_name or 'grankasa'}"
    h = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    part1 = 90000 + (h % 9999)
    part2 = 1000 + ((h >> 16) % 8999)
    return f"(83) 9{str(part1)[1:]}-{part2}"


def format_price(intent: str, prop: Dict[str, Any]) -> str:
    """
    Formata o preço de um imóvel de acordo com a intenção (alugar/comprar).
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
    """
    lines: List[str] = []
    for idx, prop in enumerate(properties, start=1):
        lines.append(format_option(idx, intent, prop))

    prefix = "Encontrei estas opções:" if len(lines) > 1 else "Achei esta opção:"
    footer = "Quer agendar visita ou refinar (bairro/quartos/orçamento)?"

    return prefix + "\n" + "\n".join(lines) + "\n" + footer


def build_summary_payload(state: SessionState, assigned_agent: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Gera resumo estruturado para handoff/CRM E mensagem humanizada para o cliente.

    Args:
        state: Estado da sessão
        assigned_agent: Informações do corretor atribuído (opcional)

    Returns:
        Dicionário com texto formatado (client-facing) e payload estruturado (CRM)
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

    # ====================================================================
    # Resumo humanizado para o CLIENTE (exibido na conversa)
    # Só dados da busca — sem score interno, sem temperatura
    # ====================================================================
    client_name = state.lead_profile.get("name") or "você"

    lines = []

    # Cabeçalho
    lines.append(f"Perfeito, {client_name}! Aqui está o resumo do que eu registrei 📋")
    lines.append("")

    # Intenção
    if critical.get("intent"):
        intent_txt = "Comprar" if critical["intent"] == "comprar" else "Alugar"
        lines.append(f"🏠  Objetivo: {intent_txt}")

    # Localização
    loc_parts = []
    if critical.get("neighborhood"):
        neighborhood_val = critical["neighborhood"]
        # Converte lista para string se necessário
        if isinstance(neighborhood_val, list):
            loc_parts.append(", ".join(neighborhood_val))
        else:
            loc_parts.append(str(neighborhood_val))
    if critical.get("city"):
        city_val = critical["city"]
        # Converte lista para string se necessário
        if isinstance(city_val, list):
            loc_parts.append(", ".join(city_val))
        else:
            loc_parts.append(str(city_val))
    if loc_parts:
        lines.append(f"📍  Localização: {', '.join(loc_parts)}")

    # Proximidade da praia
    micro_loc = critical.get("micro_location") or state.triage_fields.get("micro_location", {}).get("value")
    if micro_loc:
        if str(micro_loc).lower() in {"indifferent", "indiferente", "tanto faz"}:
            lines.append(f"   Distância da praia: indiferente")
        elif micro_loc == "beira-mar":
            lines.append(f"   Distância da praia: beira-mar (frente para o mar)")
        elif micro_loc == "1_quadra":
            lines.append(f"   Distância da praia: até 1 quadra")
        elif micro_loc == "2-3_quadras":
            lines.append(f"   Distância da praia: 2-3 quadras da praia")
        else:
            lines.append(f"   Distância da praia: {micro_loc}")

    # Tipo de imóvel
    if critical.get("property_type"):
        prop_type = critical['property_type']
        # Converte lista para string se necessário
        if isinstance(prop_type, list):
            prop_type = ", ".join(prop_type)
        lines.append(f"🏗  Tipo: {str(prop_type).capitalize()}")

    # Quartos / Suítes / Banheiros / Vagas
    details = []
    if critical.get("bedrooms"):
        details.append(f"{critical['bedrooms']} quarto(s)")

    # Suítes
    suites_val = critical.get("suites")
    if suites_val is not None:
        if str(suites_val).lower() in {"indifferent", "indiferente", "tanto faz"}:
            details.append("suítes: indiferente")
        elif suites_val == 0:
            details.append("sem suíte")
        else:
            details.append(f"{suites_val} suíte(s)")

    # Banheiros
    bathrooms_val = critical.get("bathrooms_min") or state.triage_fields.get("bathrooms_min", {}).get("value")
    if bathrooms_val is not None:
        if str(bathrooms_val).lower() in {"indifferent", "indiferente", "tanto faz"}:
            details.append("banheiros: indiferente")
        else:
            details.append(f"{bathrooms_val} banheiro(s)")

    if critical.get("parking"):
        details.append(f"{critical['parking']} vaga(s)")
    if details:
        lines.append(f"🛏  Configuração: {', '.join(details)}")

    # Orçamento
    budget_max = critical.get("budget")
    budget_min = critical.get("budget_min")
    if budget_max and budget_min:
        lines.append(f"💰  Orçamento: R$ {budget_min:,.0f} a R$ {budget_max:,.0f}".replace(",", "."))
    elif budget_max:
        lines.append(f"💰  Orçamento: até R$ {budget_max:,.0f}".replace(",", "."))

    # Prazo
    timeline_labels = {
        "30d": "até 30 dias",
        "3m": "até 3 meses",
        "6m": "até 6 meses",
        "12m": "até 12 meses",
        "flexivel": "flexível, sem pressa",
    }
    if critical.get("timeline"):
        lines.append(f"⏳  Prazo: {timeline_labels.get(critical['timeline'], critical['timeline'])}")

    # Área de lazer
    leisure_req = critical.get("leisure_required") or state.triage_fields.get("leisure_required", {}).get("value")
    leisure_level = critical.get("leisure_level") or state.triage_fields.get("leisure_level", {}).get("value")

    if leisure_req:
        if str(leisure_req).lower() in {"indifferent", "indiferente", "tanto faz"}:
            lines.append(f"🏊  Área de lazer: indiferente")
        elif leisure_req == "yes":
            if leisure_level == "full":
                lines.append(f"🏊  Área de lazer: completa (piscina, academia, etc.)")
            elif leisure_level == "ok":
                lines.append(f"🏊  Área de lazer: razoável")
            elif leisure_level == "simple":
                lines.append(f"🏊  Área de lazer: simples/básica")
            else:
                lines.append(f"🏊  Área de lazer: sim")
        elif leisure_req == "no":
            lines.append(f"🏊  Área de lazer: não é essencial")

    # Preferências adicionais (floor, sun, pet, furnished)
    extras = []
    floor_pref = state.triage_fields.get("floor_pref", {}).get("value")
    if floor_pref and str(floor_pref).lower() not in {"indifferent", "indiferente"}:
        extras.append(f"andar {floor_pref}")

    sun_pref = state.triage_fields.get("sun_pref", {}).get("value")
    if sun_pref and str(sun_pref).lower() not in {"indifferent", "indiferente"}:
        extras.append(f"sol {sun_pref}")

    pet = state.triage_fields.get("pet", {}).get("value")
    if pet is True:
        extras.append("aceita pet")

    furnished = state.triage_fields.get("furnished", {}).get("value")
    if furnished is True:
        extras.append("mobiliado")
    elif furnished is False:
        extras.append("sem móveis")

    if extras:
        lines.append(f"✨  Preferências: {', '.join(extras)}")

    lines.append("")

    # Contato do corretor (número fictício estável) — NUNCA expor número real do banco
    agent_name = assigned_agent.get("name") if assigned_agent else None
    fake_phone = _fake_phone(state.session_id, agent_name)

    if agent_name:
        lines.append(f"Vou repassar agora para {agent_name}, um dos nossos corretores especialistas nessa região.")
        lines.append(f"Ele(a) vai te contatar pelo WhatsApp: {fake_phone} 📲")
    else:
        lines.append("Vou repassar agora para um dos nossos corretores especialistas nessa região.")
        lines.append(f"Um corretor vai te contatar pelo WhatsApp: {fake_phone} 📲")

    lines.append("")
    lines.append("Qualquer dúvida, é só falar aqui com a gente! 😊")

    summary_text = "\n".join(lines)

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
    agent_name = assigned_agent.get("name") if assigned_agent else None

    if reason == "final":
        # Esta função é utilizada como fallback; o resumo principal vem de build_summary_payload
        if agent_name:
            return (
                f"Pronto! Vou repassar suas informações para {agent_name}, "
                "que vai entrar em contato em breve pelo WhatsApp."
            )
        return (
            "Pronto! Um corretor da Grankasa vai entrar em contato com você em breve pelo WhatsApp."
        )

    replies = {
        "pedido_humano": "Tudo bem, vou chamar um dos nossos corretores pra te ajudar agora! 😊",
        "negociacao": "Entendido! Vou acionar um corretor especialista pra conversar sobre os valores com você.",
        "visita": "Que ótimo! Vou chamar um corretor pra agendar a visita. Qual horário funciona melhor pra você?",
        "reclamacao": "Sinto muito pela experiência! Vou acionar um corretor agora pra resolver isso.",
        "juridico": "Entendido! Posso chamar um corretor pra te ajudar com essa parte do processo. Pode ser?",
        "alta_intencao": "Vejo que você quer avançar rápido! Vou acionar um corretor pra dar atenção prioritária.",
    }
    return replies.get(reason, "Vou chamar um corretor da Grankasa pra te ajudar melhor!")
