from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from .state import store, SessionState
from .ai_agent import get_agent
from . import tools
from .rules import (
    can_search_properties,
    missing_critical_fields,
    next_best_question,
    next_best_question_key,
    choose_question,
    QUESTION_BANK,
    PREFERENCE_ORDER,
)
from .dialogue import Plan
from .llm import TRIAGE_ONLY
from .extractor import enrich_with_regex
from .presenter import (
    format_option,
    build_summary_payload,
    format_handoff_message,
)
from .scoring import compute_lead_score
from .persistence import persist_state


AFFIRMATIVE = {"sim", "s", "pode", "claro", "ok", "yes", "isso", "perfeito"}
NEGATIVE = {"nao", "não", "n", "no", "negativo"}
BOOL_KEYS = {"pet", "furnished"}


def _human_handoff(state: SessionState, reason: str) -> Dict[str, Any]:
    """Processa handoff para humano usando presenter para formatar mensagem."""
    state.human_handoff = True
    summary = {
        "session_id": state.session_id,
        "intent": state.intent,
        "criteria": state.criteria.__dict__,
        "last_suggestions": state.last_suggestions,
        "reason": reason,
        "lead_score": state.lead_score.__dict__,
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
    """
    agent = get_agent()

    try:
        should_handoff, reason, urgency = agent.should_handoff(message, state)
        if should_handoff:
            print(f"[HANDOFF] Handoff detectado: {reason} (urgência: {urgency})")
        return should_handoff, reason
    except Exception as e:
        print(f"[WARN] Erro na decisão de handoff, usando fallback do agent: {e}")
        should_handoff, reason, _ = agent._handoff_fallback(message, state)
        return should_handoff, reason


def _short_reply_updates(message: str, state: SessionState) -> Dict[str, Dict[str, Any]]:
    """
    Interpreta respostas curtas como confirmação do último campo.
    """
    msg = message.strip().lower()
    updates: Dict[str, Dict[str, Any]] = {}
    lk = state.last_question_key
    if not lk:
        return updates

    is_yes = msg in AFFIRMATIVE
    is_no = msg in NEGATIVE

    if lk == "city_confirm" and (is_yes or is_no):
        city_val = state.criteria.city or state.triage_fields.get("city", {}).get("value")
        updates["city"] = {"value": city_val if is_yes else None, "status": "confirmed", "source": "user"}
        return updates

    if lk in BOOL_KEYS and (is_yes or is_no):
        updates[lk] = {"value": True if is_yes else False, "status": "confirmed", "source": "user"}
        return updates

    return updates


def _avoid_repeat_question(state: SessionState, proposed_key: Optional[str]) -> Optional[str]:
    if not proposed_key:
        return proposed_key
    if state.last_question_key and state.last_question_key == proposed_key:
        missing = missing_critical_fields(state)
        for key in missing:
            if key != proposed_key and key not in state.asked_questions:
                return key
    return proposed_key


def _question_text_for_key(key: Optional[str], state: SessionState) -> str:
    if not key:
        return "Como posso ajudar?"
    question = choose_question(key, state)
    if question:
        return question
    return QUESTION_BANK.get(key, ["Pode me dar mais detalhes?"])[0]


def handle_message(session_id: str, message: str, name: str | None = None, correlation_id: str | None = None) -> Dict[str, Any]:
    """
    Processa mensagem do cliente (máx 1 chamada LLM).
    """
    agent = get_agent()
    state = store.get(session_id)
    triage_only = TRIAGE_ONLY

    if name and not state.lead_profile.get("name"):
        state.lead_profile["name"] = name
        state.lead_name = name

    state.history.append({"role": "user", "text": message})

    # Heurística para respostas curtas (sim/não)
    user_short_updates = _short_reply_updates(message, state)

    neighborhoods = tools.get_neighborhoods()
    decision, used_llm = agent.decide(message, state, neighborhoods, correlation_id=correlation_id)

    low_msg = message.lower()
    override_phrase = "na verdade" in low_msg or "corrig" in low_msg
    override_intent = None
    if override_phrase:
        if "comprar" in low_msg:
            override_intent = "comprar"
        elif "alugar" in low_msg or "aluguel" in low_msg:
            override_intent = "alugar"

    new_intent = decision.get("intent")
    extracted = decision.get("criteria", {}) or {}
    extracted_updates = decision.get("extracted_updates") or {k: {"value": v, "status": "confirmed"} for k, v in extracted.items()}
    handoff_info = decision.get("handoff", {})
    plan_info = decision.get("plan", {})
    fallback_reason = decision.get("fallback_reason")
    if fallback_reason:
        state.fallback_reason = fallback_reason

    # Atualiza/override intent
    if override_intent and state.intent and override_intent != state.intent:
        extracted_updates["intent"] = {"value": override_intent, "status": "override", "source": "user"}
        state.intent = override_intent
    if new_intent and not state.intent:
        state.intent = new_intent
        print(f"[INTENT] Intent: {new_intent}")

    # Merge updates: regex enrichment + short replies
    extracted_updates = enrich_with_regex(message, state, extracted_updates)
    if user_short_updates:
        extracted_updates.update(user_short_updates)

    conflicts, conflict_values = state.apply_updates(extracted_updates)

    if extracted:
        print(f"[CRITERIA] Critérios: {extracted}")

    # Aplica lead scoring a cada mensagem
    score = compute_lead_score(state)
    state.lead_score.temperature = score["temperature"]
    state.lead_score.score = score["score"]
    state.lead_score.reasons = score["reasons"]
    print(f"[LEAD_SCORE] score={score['score']} temp={score['temperature']} reasons={score['reasons']} correlation={correlation_id}")

    # Handoff (regras IA + decisão)
    if handoff_info.get("should"):
        reason = handoff_info.get("reason", "outro")
        print(f"[HANDOFF] Handoff: {reason}")
        return _human_handoff(state, reason=reason)

    # === TRIAGEM ONLY ===
    if triage_only:
        if conflicts:
            key = conflicts[0]
            vals = conflict_values.get(key, {})
            prev_val = vals.get("previous") if vals else state.triage_fields.get(key, {}).get("value")
            new_val = vals.get("new") if vals else extracted_updates.get(key, {}).get("value")
            question = f"Notei duas respostas diferentes para {key}: {prev_val} vs {new_val}. Qual vale?"
            state.last_question_key = key
            if key not in state.asked_questions:
                state.asked_questions.append(key)
            state.history.append({"role": "assistant", "text": question})
            return {"reply": question, "state": state.to_public_dict()}

        missing = missing_critical_fields(state)
        if missing:
            next_key = next_best_question_key(state)
            next_key = _avoid_repeat_question(state, next_key)
            question = _question_text_for_key(next_key, state)
            state.last_question_key = next_key
            if next_key and next_key not in state.asked_questions:
                state.asked_questions.append(next_key)
            reply = question
            if state.fallback_reason:
                reply = f"Vou seguir no modo simples: {question}"
            state.history.append({"role": "assistant", "text": reply})
            return {"reply": reply, "state": state.to_public_dict()}

        # Triagem concluída
        summary = build_summary_payload(state)
        summary["payload"]["lead_score"] = state.lead_score.__dict__
        state.completed = True
        persist_state(state)
        state.history.append({"role": "assistant", "text": summary["text"]})
        return {
            "reply": summary["text"],
            "state": state.to_public_dict(),
            "summary": summary["payload"],
            "handoff": tools.handoff_human(str(summary["payload"]))
        }

    # === FLUXO NORMAL (não usado neste MVP, mas mantido) ===
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

    if plan.action not in {"ASK", "SEARCH", "LIST", "REFINE", "SCHEDULE", "HANDOFF", "ANSWER_GENERAL", "CLARIFY", "TRIAGE_SUMMARY"}:
        plan.action = "ASK"

    if plan.action in {"SEARCH", "LIST"} and not can_search_properties(state):
        missing = missing_critical_fields(state)
        if missing:
            plan.action = "ASK"
            plan.message = choose_question(missing[0], state) or "Pode me dizer a cidade e o orçamento?"

    updates = plan.state_updates or {}
    if "intent" in updates and updates["intent"]:
        state.intent = updates["intent"]
    criteria_updates = updates.get("criteria") or {}
    for key, value in criteria_updates.items():
        if value is not None:
            state.set_criterion(key, value, status="confirmed")

    if plan.action == "HANDOFF" and plan.handoff_reason:
        return _human_handoff(state, reason=plan.handoff_reason)

    if plan.action in {"ASK", "REFINE", "CLARIFY"}:
        qkey = _avoid_repeat_question(state, plan.question_key or state.last_question_key)
        if qkey and choose_question(qkey, state):
            reply = choose_question(qkey, state)
        else:
            reply = plan.question or plan.message or "Como posso ajudar?"
        if state.fallback_reason:
            reply = f"Vou seguir no modo simples: {reply}"
        state.last_question_key = qkey or plan.question_key or state.last_question_key
        if state.last_question_key and state.last_question_key not in state.asked_questions:
            state.asked_questions.append(state.last_question_key)
        state.history.append({"role": "assistant", "text": reply})
        return {"reply": reply, "state": state.to_public_dict()}

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

    question = choose_question(next_best_question_key(state) or "", state) or plan.message or "Como posso ajudar? Prefere alugar ou comprar?"
    state.history.append({"role": "assistant", "text": question})
    return {"reply": question, "state": state.to_public_dict()}
