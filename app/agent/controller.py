from __future__ import annotations
from typing import Dict, Any, List, Tuple
from .state import store, SessionState
from .ai_agent import get_agent
from . import tools
from .rules import can_search_properties, missing_critical_fields, next_best_question, QUESTION_BANK
from .dialogue import Plan
from .llm import TRIAGE_ONLY
from .extractor import extract_criteria


HUMAN_KEYWORDS = {"humano", "atendente", "corretor"}
HUMAN_PHRASES = {"falar com alguem", "falar com uma pessoa", "pessoa de verdade", "humano de verdade"}
NEGOTIATION_KEYWORDS = {"desconto", "negociar", "baixar preco", "consegue baixar", "melhorar preco", "faz por", "baixa pra"}
VISIT_KEYWORDS = {"visita", "visitar", "agendar visita", "tour", "ver pessoalmente", "presencial", "virtual", "agendar", "marcar"}
IRRITATION_KEYWORDS = {"reclamacao", "reclamação", "péssimo", "pessimo", "nao gostei", "horrivel", "ruim", "cancelar", "odio", "odiei"}
LEGAL_KEYWORDS = {"contrato", "clausula", "cláusula", "processo", "acao judicial", "ação judicial", "advogado", "documentacao", "documentação"}

CRITICAL_ORDER = ["intent", "city", "neighborhood", "property_type", "bedrooms", "parking", "budget", "timeline"]


def _apply_extracted_updates(state: SessionState, updates: Dict[str, Any]) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    """Aplica updates extraídos ao estado, retornando conflitos e seus valores."""
    conflicts: List[str] = []
    conflict_values: Dict[str, Dict[str, Any]] = {}
    for key, payload in (updates or {}).items():
        if payload is None:
            continue
        value = payload.get("value") if isinstance(payload, dict) else payload
        status = payload.get("status", "confirmed") if isinstance(payload, dict) else "confirmed"
        # Intent pode vir separada
        if key == "intent":
            if state.intent and value and state.intent != value and state.intent in {"comprar", "alugar"}:
                conflicts.append("intent")
                conflict_values["intent"] = {"previous": state.intent, "new": value}
            elif value:
                state.intent = value
            continue
        prev = state.triage_fields.get(key, {})
        prev_val = prev.get("value")
        prev_status = prev.get("status")
        if prev_status == "confirmed" and value is not None and prev_val not in (None, value):
            conflicts.append(key)
            conflict_values[key] = {"previous": prev_val, "new": value}
            continue  # não sobrescreve; precisa clarificar
        state.set_triage_field(key, value, status=status)
    return conflicts, conflict_values


def _enrich_with_regex(message: str, state: SessionState, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Usa extractor determinístico para capturar campos que o LLM não trouxe.
    Apenas preenche campos ausentes.
    """
    fallback = extract_criteria(message, [])
    merged = dict(updates)
    for k, v in fallback.items():
        if v is None:
            continue
        current = merged.get(k)
        already_set = state.triage_fields.get(k)
        if (not current or current.get("value") is None) and not (already_set and already_set.get("status") == "confirmed"):
            merged[k] = {"value": v, "status": "confirmed"}
    return merged


def _build_summary_payload(state: SessionState) -> Dict[str, Any]:
    """Gera resumo estruturado para handoff/CRM."""
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
        "lead_name": state.lead_name,
        "critical": critical,
        "preferences": preferences,
        "status": "triage_completed",
    }

    # Texto curto para humano
    txt_parts = []
    if critical.get("intent"):
        txt_parts.append(f"Operação: {critical['intent']}")
    if critical.get("city"):
        txt_parts.append(f"Cidade: {critical['city']}")
    if critical.get("neighborhood") is not None:
        txt_parts.append(f"Bairro: {critical['neighborhood'] or 'sem preferência'}")
    if critical.get("property_type"):
        txt_parts.append(f"Tipo: {critical['property_type']}")
    if critical.get("bedrooms"):
        txt_parts.append(f"Quartos: {critical['bedrooms']}")
    if critical.get("parking"):
        txt_parts.append(f"Vagas: {critical['parking']}")
    if critical.get("budget"):
        txt_parts.append(f"Orçamento máx.: R$ {critical['budget']}")
    if critical.get("timeline"):
        txt_parts.append(f"Prazo: {critical['timeline']}")

    summary_text = "Resumo da triagem:\n- " + "\n- ".join(txt_parts) if txt_parts else "Triagem concluída."

    return {"text": summary_text, "payload": summary_json}


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
    replies = {
        "pedido_humano": "Tudo bem, vou te passar para um corretor agora.",
        "negociacao": "Vou acionar um corretor para tratar do valor e te responder rapidinho.",
        "visita": "Vou chamar um corretor para agendar a visita. Qual horário funciona melhor?",
        "reclamacao": "Sinto muito pela experiência. Vou passar para um corretor resolver agora.",
        "juridico": "Posso pedir para um corretor te ajudar com essa parte contratual. Pode ser?",
        "alta_intencao": "Vejo que você quer fechar rápido. Posso acionar um corretor para agilizar?",
    }
    reply = replies.get(reason, "Vou acionar um corretor humano para te ajudar melhor.")
    return {
        "reply": reply,
        "handoff": tools.handoff_human(str(summary)),
        "state": state.to_public_dict(),
    }


def should_handoff_to_human(message: str, state: SessionState) -> Tuple[bool, str]:
    """
    Decide se deve transferir para humano usando análise de IA.
    
    Antes: usava keywords hardcoded
    Agora: usa LLM para análise contextual inteligente
    """
    agent = get_agent()
    
    try:
        should_handoff, reason, urgency = agent.should_handoff(message, state)
        
        # Log para debug
        if should_handoff:
            print(f"[HANDOFF] Handoff detectado: {reason} (urgência: {urgency})")
        
        return should_handoff, reason
    except Exception as e:
        print(f"[WARN] Erro na decisão de handoff, usando fallback: {e}")
        # Fallback para detecção simples por keywords em caso de erro
        return _handoff_fallback_simple(message, state)


def _handoff_fallback_simple(message: str, state: SessionState) -> Tuple[bool, str]:
    """Fallback simples baseado em keywords (usado em caso de erro)"""
    import unicodedata
    
    def strip_accents(text: str) -> str:
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    
    low = strip_accents(message.lower())
    
    if any(k in low for k in ["humano", "atendente", "corretor"]):
        return True, "pedido_humano"
    if any(k in low for k in ["desconto", "negociar", "baixar"]):
        return True, "negociacao"
    if any(k in low for k in ["visita", "visitar", "agendar"]):
        return True, "visita"
    if any(k in low for k in ["reclamacao", "pessimo", "ruim"]):
        return True, "reclamacao"
    if any(k in low for k in ["contrato", "juridico", "advogado"]):
        return True, "juridico"
    
    if state.criteria.budget and state.criteria.urgency == "alta" and state.intent in {"comprar", "alugar"}:
        return True, "alta_intencao"
    
    return False, ""


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
    extracted_updates = _enrich_with_regex(message, state, extracted_updates)

    conflicts, conflict_values = _apply_extracted_updates(state, extracted_updates)

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
        summary = _build_summary_payload(state)
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
            lines.append(_format_option(idx, state.intent, prop))

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
