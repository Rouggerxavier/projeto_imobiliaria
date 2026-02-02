from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from .state import store, SessionState
from .ai_agent import get_agent
from . import tools
from .rules import can_search_properties, missing_critical_fields, QUESTION_BANK
from .dialogue import Plan
from .llm import TRIAGE_ONLY
from .extractor import enrich_with_regex
from .presenter import (
    format_option,
    build_summary_payload,
    format_handoff_message,
)



def _human_handoff(state: SessionState, reason: str) -> Dict[str, Any]:
    """Processa handoff para humano usando presenter para formatar mensagem."""
    state.human_handoff = True
    summary = {
        "session_id": state.session_id,
        "intent": state.intent,
        "criteria": state.criteria.__dict__,
        "last_suggestions": state.last_suggestions,
        "reason": reason,
    }
    reply = format_handoff_message(reason)
    return {
        "reply": reply,
        "handoff": tools.handoff_human(str(summary)),
        "state": state.to_public_dict(),
    }


def should_handoff_to_human(message: str, state: SessionState) -> Tuple[bool, str]:
    """
    Decide se deve transferir para humano usando análise de IA.

    Usa o método should_handoff do ai_agent que já tem fallback integrado.
    """
    agent = get_agent()

    try:
        should_handoff, reason, urgency = agent.should_handoff(message, state)

        # Log para debug
        if should_handoff:
            print(f"[HANDOFF] Handoff detectado: {reason} (urgência: {urgency})")

        return should_handoff, reason
    except Exception as e:
        print(f"[WARN] Erro na decisão de handoff, usando fallback do agent: {e}")
        # O ai_agent.should_handoff já tem seu próprio fallback (_handoff_fallback)
        # Então delegamos para ele em caso de erro
        should_handoff, reason, _ = agent._handoff_fallback(message, state)
        return should_handoff, reason


def ask_next_question(state: SessionState) -> str | None:
    if not state.intent:
        # Greeting only on the first bot reply.
        if len(state.history) == 1:
            if state.criteria.city:
                return f"Bom dia! Você quer alugar ou comprar um imóvel em {state.criteria.city}?"
            return "Bom dia! Você quer alugar ou comprar?"
        if state.criteria.city:
            return f"Você quer alugar ou comprar um imóvel em {state.criteria.city}?"
        return "Você quer alugar ou comprar?"

    missing = missing_critical_fields(state)
    if not missing:
        return None
    first = missing[0]
    if first == "location":
        return "Qual cidade ou bairro você prefere?"
    if first == "budget":
        return "Qual o orçamento máximo? Pode ser aproximado."
    if first == "property_type":
        return "Prefere apartamento, casa ou outro tipo?"
    return None


def _avoid_repeat_question(state: SessionState, proposed_key: Optional[str]) -> Optional[str]:
    """Se já perguntou recentemente o mesmo campo, tenta o próximo faltante."""
    if not proposed_key:
        return proposed_key
    if state.last_question_key and state.last_question_key == proposed_key:
        missing = missing_critical_fields(state)
        for key in missing:
            if key != proposed_key and key not in state.asked_questions:
                return key
    return proposed_key


def handle_message(session_id: str, message: str, name: str | None = None, correlation_id: str | None = None) -> Dict[str, Any]:
    """
    Processa mensagem do cliente.

    OTIMIZAÇÃO: Faz NO MÁXIMO 1 chamada LLM por mensagem.

    Fluxo:
    1. Carrega estado da sessão
    2. Chama agent.decide() - UMA única chamada que retorna tudo
    3. Aplica decisão (handoff, busca, pergunta, etc)
    """
    agent = get_agent()
    state = store.get(session_id)
    triage_only = TRIAGE_ONLY

    # Atualiza nome do lead se fornecido
    if name and not state.lead_name:
        state.lead_name = name

    # Adiciona mensagem ao histórico
    state.history.append({"role": "user", "text": message})

    # [PLAN] DECISÃO ÚNICA - Faz tudo em 1 chamada (ou fallback)
    neighborhoods = tools.get_neighborhoods()
    decision, used_llm = agent.decide(message, state, neighborhoods, correlation_id=correlation_id)

    # Extrai partes da decisão
    new_intent = decision.get("intent")
    extracted = decision.get("criteria", {}) or {}
    extracted_updates = decision.get("extracted_updates") or {k: {"value": v, "status": "confirmed"} for k, v in extracted.items()}
    handoff_info = decision.get("handoff", {})
    plan_info = decision.get("plan", {})
    fallback_reason = decision.get("fallback_reason")
    if fallback_reason:
        state.fallback_reason = fallback_reason

    # Atualiza intent se veio novo
    if new_intent and not state.intent:
        state.intent = new_intent
        print(f"[INTENT] Intent: {new_intent}")

    # Aplica updates extraídos (críticos e preferências)
    # Enriquecimento determinístico para garantir captura de múltiplas infos na mesma mensagem
    extracted_updates = enrich_with_regex(message, state, extracted_updates)

    conflicts, conflict_values = state.apply_updates(extracted_updates)

    if extracted:
        print(f"[CRITERIA] Critérios: {extracted}")

    # Verifica handoff
    if handoff_info.get("should"):
        reason = handoff_info.get("reason", "outro")
        print(f"[HANDOFF] Handoff: {reason}")
        return _human_handoff(state, reason=reason)

    # --- MODO TRIAGEM-ONLY ---
    if triage_only:
        # Contradições geram CLARIFY
        if conflicts:
            key = conflicts[0]
            vals = conflict_values.get(key, {})
            prev_val = vals.get("previous") if vals else state.triage_fields.get(key, {}).get("value")
            new_val = vals.get("new") if vals else extracted_updates.get(key, {}).get("value")
            question = f"Você prefere confirmar {key} como {new_val} ou manter {prev_val}?"
            state.last_question_key = key
            if key not in state.asked_questions:
                state.asked_questions.append(key)
            state.history.append({"role": "assistant", "text": question})
            return {"reply": question, "state": state.to_public_dict()}

        missing = missing_critical_fields(state)
        if missing:
            next_key = next((k for k in missing if k not in state.asked_questions), missing[0])
            question = QUESTION_BANK.get(next_key) or ask_next_question(state) or "Pode me dar mais detalhes?"
            state.last_question_key = next_key
            if next_key not in state.asked_questions:
                state.asked_questions.append(next_key)
            reply = question
            if state.fallback_reason:
                reply = f"Estou com limitação temporária do modelo. Vou seguir no modo simples: {question}"
            state.history.append({"role": "assistant", "text": reply})
            return {"reply": reply, "state": state.to_public_dict()}

        # Triagem concluída -> resumo estruturado
        summary = build_summary_payload(state)
        state.completed = True
        state.history.append({"role": "assistant", "text": summary["text"]})
        return {
            "reply": summary["text"],
            "state": state.to_public_dict(),
            "summary": summary["payload"],
            "handoff": tools.handoff_human(str(summary["payload"]))
        }

    # --- FLUXO NORMAL (não triagem) ---
    # Converte plan_info para Plan (reutiliza estrutura existente)
    plan = Plan(
        action=plan_info.get("action", "ASK"),
        message=plan_info.get("message", ""),
        question_key=plan_info.get("question_key"),
        question=plan_info.get("question") or plan_info.get("message"),
        filters=plan_info.get("filters", {}),
        handoff_reason=plan_info.get("handoff_reason"),
        state_updates=plan_info.get("state_updates", {}),
        reasoning=plan_info.get("reasoning")
    )

    print(f"[PLAN] Plano: {plan.action} - {plan.reasoning or plan.message[:50]}")

    # Guard-rail: valida action
    if plan.action not in {"ASK", "SEARCH", "LIST", "REFINE", "SCHEDULE", "HANDOFF", "ANSWER_GENERAL", "CLARIFY", "TRIAGE_SUMMARY"}:
        plan.action = "ASK"

    # Guard-rail: Se SEARCH mas não pode buscar, força ASK
    if plan.action in {"SEARCH", "LIST"} and not can_search_properties(state):
        missing = missing_critical_fields(state)
        if missing:
            plan.action = "ASK"
            plan.message = ask_next_question(state) or "Pode me dizer a cidade e o orçamento?"

    # Aplica state_updates se houver
    updates = plan.state_updates or {}
    if "intent" in updates and updates["intent"]:
        state.intent = updates["intent"]
    criteria_updates = updates.get("criteria") or {}
    for key, value in criteria_updates.items():
        if value is not None:
            state.set_criterion(key, value, status="confirmed")

    # Executa ação baseada no plano
    if plan.action == "HANDOFF" and plan.handoff_reason:
        return _human_handoff(state, reason=plan.handoff_reason)

    if plan.action in {"ASK", "REFINE", "CLARIFY"}:
        qkey = _avoid_repeat_question(state, plan.question_key or state.last_question_key)
        if qkey and qkey in QUESTION_BANK:
            reply = QUESTION_BANK[qkey]
        else:
            reply = plan.question or plan.message or ask_next_question(state) or "Como posso ajudar?"
        if state.fallback_reason:
            prefix_map = {
                "QUOTA_EXHAUSTED_DAILY": "Minha cota do modelo acabou por agora. Vou seguir no modo simples:",
                "RATE_LIMIT_RPM": "Estou com limite de requisições. Vou continuar no modo simples:",
                "RATE_LIMIT_TPM": "Estou com limite de tokens. Vou continuar no modo simples:",
                "AUTH_INVALID_KEY": "Parece haver um problema na chave da IA. Vou continuar no modo simples:",
                "AUTH_PERMISSION_DENIED": "Parece haver um bloqueio de permissão da IA. Vou seguir no modo simples:",
                "BILLING_REQUIRED": "Preciso de ajustes de billing da IA. Vou seguir no modo simples:",
            }
            prefix = prefix_map.get(state.fallback_reason, "Estou com limitação temporária do modelo. Continuo em modo simples:")
            reply = f"{prefix} {reply}"
        state.last_question_key = qkey or plan.question_key or state.last_question_key
        if state.last_question_key and state.last_question_key not in state.asked_questions:
            state.asked_questions.append(state.last_question_key)
        state.history.append({"role": "assistant", "text": reply})
        response = {"reply": reply, "state": state.to_public_dict()}
        return response

    if plan.action == "ANSWER_GENERAL":
        reply = plan.message or "Como posso ajudar?"
        state.history.append({"role": "assistant", "text": reply})
        return {"reply": reply, "state": state.to_public_dict()}

    if plan.action in {"SEARCH", "LIST"}:
        filters = plan.filters or {
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
            reply = "Não encontrei opções com esses filtros. Posso aumentar o orçamento em ~10% ou considerar bairros vizinhos?"
            state.history.append({"role": "assistant", "text": reply})
            return {"reply": reply, "state": state.to_public_dict()}

        state.last_suggestions = [r.get("id") for r in results]
        lines: List[str] = []
        for idx, prop in enumerate(results, start=1):
            lines.append(format_option(idx, state.intent, prop))

        prefix = plan.message or ("Encontrei estas opções:" if len(lines) > 1 else "Achei esta opção:")
        footer = "Quer agendar visita ou refinar (bairro/quartos/orçamento)?"
        reply = prefix + "\n" + "\n".join(lines) + "\n" + footer
        state.stage = "apresentou_opcoes"
        state.history.append({"role": "assistant", "text": reply})
        return {"reply": reply, "state": state.to_public_dict(), "properties": state.last_suggestions}

    if plan.action == "SCHEDULE":
        reply = plan.message or "Posso agendar uma visita. Qual horário prefere?"
        state.history.append({"role": "assistant", "text": reply})
        return {"reply": reply, "state": state.to_public_dict()}

    # Default fallback
    question = ask_next_question(state)
    reply = question or plan.message or "Como posso ajudar? Prefere alugar ou comprar?"
    state.history.append({"role": "assistant", "text": reply})
    return {"reply": reply, "state": state.to_public_dict()}
