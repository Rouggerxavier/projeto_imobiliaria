from __future__ import annotations
from typing import Dict, Any, List
from .state import store, SessionState
from .intent import classify_intent
from .extractor import extract_criteria
from . import tools
from .rules import can_search_properties, can_answer_about_property, next_best_question, missing_critical_fields

NEGOTIATION_KEYWORDS = {"desconto", "negociar", "baixar preco", "proposta", "contraproposta"}
VISIT_KEYWORDS = {"visita", "visitar", "tour", "ver pessoalmente", "presencial", "virtual"}
HUMAN_KEYWORDS = {"humano", "atendente", "corretor", "pessoa", "falar com alguem"}


def _format_price(intent: str, prop: Dict[str, Any]) -> str:
    if intent == "alugar":
        price = prop.get("preco_aluguel")
        if price:
            return f"R${price:,.0f}/mes".replace(",", ".")
    else:
        price = prop.get("preco_venda")
        if price:
            return f"R${price:,.0f}".replace(",", ".")
    return "Consulte"


def _format_option(idx: int, intent: str, prop: Dict[str, Any]) -> str:
    price_txt = _format_price(intent, prop)
    return (
        f"{idx}) {prop.get('titulo')} - {prop.get('bairro')}/{prop.get('cidade')}\n"
        f"   {prop.get('quartos')}q • {prop.get('vagas')} vaga(s) • {prop.get('area_m2')} m²\n"
        f"   {price_txt} • {prop.get('descricao_curta')}"
    )


def _human_handoff(state: SessionState, reason: str) -> Dict[str, Any]:
    state.human_handoff = True
    summary = {
        "session_id": state.session_id,
        "intent": state.intent,
        "criteria": state.criteria.__dict__,
        "last_suggestions": state.last_suggestions,
        "reason": reason,
    }
    return {
        "reply": "Vou acionar um corretor humano para te ajudar melhor. Em instantes ele assume por aqui.",
        "handoff": tools.handoff_human(str(summary)),
        "state": state.to_public_dict(),
    }


def _needs_handoff(message: str, state: SessionState) -> bool:
    low = message.lower()
    if any(k in low for k in NEGOTIATION_KEYWORDS):
        return True
    if any(k in low for k in HUMAN_KEYWORDS):
        return True
    if state.criteria.budget and state.criteria.urgency == "alta" and state.intent in {"comprar", "alugar"}:
        return True
    return False


def _maybe_schedule(message: str, state: SessionState) -> Dict[str, Any] | None:
    low = message.lower()
    if any(k in low for k in VISIT_KEYWORDS):
        if not state.last_suggestions:
            return {"reply": "Qual imovel voce quer visitar? Te passo as opcoes e ja vejo horarios."}
        options = ", ".join([prop_id for prop_id in state.last_suggestions])
        return {
            "reply": (
                "Perfeito! Qual destes imoveis voce quer visitar (id)? "
                f"{options}. Pode mandar 2-3 janelas de horario e se prefere presencial ou virtual."
            )
        }
    return None


def handle_message(session_id: str, message: str, name: str | None = None) -> Dict[str, Any]:
    state = store.get(session_id)
    if name and not state.lead_name:
        state.lead_name = name
    state.history.append({"role": "user", "text": message})

    new_intent = classify_intent(message) or state.intent
    state.intent = new_intent

    neighborhoods = tools.get_neighborhoods()
    extracted = extract_criteria(message, neighborhoods)
    for key, value in extracted.items():
        state.set_criterion(key, value, status="confirmed")

    if _needs_handoff(message, state):
        return _human_handoff(state, reason="pedido_expresso")

    schedule_msg = _maybe_schedule(message, state)
    if schedule_msg:
        return {**schedule_msg, "state": state.to_public_dict()}

    if not state.intent:
        reply = "Posso ajudar a comprar ou alugar. O que você procura hoje?"
        return {"reply": reply, "state": state.to_public_dict()}

    missing = missing_critical_fields(state)
    if missing:
        question = next_best_question(state)
        return {"reply": question, "state": state.to_public_dict()}

    if can_search_properties(state):
        filters = {
            "city": state.criteria.city,
            "neighborhood": state.criteria.neighborhood,
            "property_type": state.criteria.property_type,
            "bedrooms": state.criteria.bedrooms,
            "pet": state.criteria.pet,
            "furnished": state.criteria.furnished,
            "budget": state.criteria.budget,
        }
        results = tools.search_properties(filters, intent=state.intent)
        if not results:
            reply = (
                "Não encontrei opções com esses filtros. Posso aumentar o orçamento em ~10% ou considerar bairros vizinhos?"
            )
            return {"reply": reply, "state": state.to_public_dict()}

        state.last_suggestions = [r.get("id") for r in results]
        lines: List[str] = []
        for idx, prop in enumerate(results, start=1):
            lines.append(_format_option(idx, state.intent, prop))
        prefix = (
            "Encontrei estas opções que batem com o que você pediu:" if len(lines) > 1 else "Achei esta opção:"
        )
        footer = "Quer agendar visita ou refinar (bairro/quartos/orçamento)?"
        reply = prefix + "\n" + "\n".join(lines) + "\n" + footer
        state.stage = "apresentou_opcoes"
        return {"reply": reply, "state": state.to_public_dict(), "properties": state.last_suggestions}

    reply = "Vou te ajudar melhor se me disser a cidade/bairro e o orçamento aproximado."
    return {"reply": reply, "state": state.to_public_dict()}
