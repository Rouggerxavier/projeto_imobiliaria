from __future__ import annotations
import logging
from typing import Dict, Any, List, Tuple, Optional
import time

logger = logging.getLogger(__name__)
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
from . import llm as llm_module
from .extractor import enrich_with_regex, resolve_city
from .presenter import (
    format_option,
    build_summary_payload,
    format_handoff_message,
)
from .scoring import compute_lead_score
from .persistence import persist_state
from . import persistence
from .router import route_lead
from .quality import compute_quality_score
from app import faq


AFFIRMATIVE = {"sim", "s", "pode", "claro", "ok", "yes", "isso", "perfeito"}
NEGATIVE = {"nao", "não", "n", "no", "negativo"}
BOOL_KEYS = {"pet", "furnished"}
GREETINGS = {"bom dia", "boa tarde", "boa noite", "olá", "ola", "oi", "e aí", "eai"}
INTENT_KEYWORDS = {"comprar", "alugar", "investir"}
GENERIC_NAMES = {"ok", "ola", "olá", "oi", "hi", "hello", "tudo bem"}

# Saudão inicial da Grankasa — exibida apenas no primeiro turno quando é só cumprimento
_GRANKASA_GREETING = (
    "Bom dia! 😊 Só pra me apresentar: sou a assistente virtual da Grankasa. "
    "Estamos aqui pra te ajudar a encontrar o imóvel ideal! "
    "Me conta, você está buscando algo pra comprar ou pra alugar?"
)
_GRANKASA_GREETING_TARDE = (
    "Boa tarde! 😊 Só pra me apresentar: sou a assistente virtual da Grankasa. "
    "Estamos aqui pra te ajudar a encontrar o imóvel ideal! "
    "Me conta, você está buscando algo pra comprar ou pra alugar?"
)
_GRANKASA_GREETING_NOITE = (
    "Boa noite! 😊 Só pra me apresentar: sou a assistente virtual da Grankasa. "
    "Estamos aqui pra te ajudar a encontrar o imóvel ideal! "
    "Me conta, você está buscando algo pra comprar ou pra alugar?"
)
_GRANKASA_GREETING_NEUTRAL = (
    "Olá! 😊 Só pra me apresentar: sou a assistente virtual da Grankasa. "
    "Estamos aqui pra te ajudar a encontrar o imóvel ideal! "
    "Me conta, você está buscando algo pra comprar ou pra alugar?"
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
            logger.info("Handoff detectado: %s (urgência: %s)", reason, urgency)
        return should_handoff, reason
    except Exception as e:
        logger.warning("Erro na decisão de handoff, usando fallback do agent: %s", e)
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
    is_indifferent = any(kw in msg for kw in ["tanto faz", "indiferente", "qualquer", "nao importa", "não importa"])

    # Detecta "indiferente" para qualquer campo
    if is_indifferent:
        if lk in {"suites", "bathrooms_min", "micro_location", "leisure_required", "leisure_level", "floor_pref", "sun_pref", "pet", "furnished"}:
            updates[lk] = {"value": "indifferent", "status": "confirmed", "source": "user", "raw_text": message}
            return updates

    if lk in BOOL_KEYS and (is_yes or is_no):
        updates[lk] = {"value": True if is_yes else False, "status": "confirmed", "source": "user"}
        return updates

    # NOVO: Suítes (aceita números ou "nenhuma")
    if lk == "suites":
        import re
        # Padrões: "1", "2", "nenhuma", "0"
        match = re.search(r"(\d+)", msg)
        if match:
            updates["suites"] = {"value": int(match.group(1)), "status": "confirmed", "source": "user", "raw_text": message}
            return updates
        if "nenhuma" in msg or "sem" in msg or "zero" in msg:
            updates["suites"] = {"value": 0, "status": "confirmed", "source": "user", "raw_text": message}
            return updates

    # NOVO: Banheiros
    if lk == "bathrooms_min":
        import re
        match = re.search(r"(\d+)", msg)
        if match:
            updates["bathrooms_min"] = {"value": int(match.group(1)), "status": "confirmed", "source": "user", "raw_text": message}
            return updates

    # NOVO: Micro-location (praia)
    if lk == "micro_location":
        if "beira" in msg or "frente" in msg:
            updates["micro_location"] = {"value": "beira-mar", "status": "confirmed", "source": "user", "raw_text": message}
            return updates
        if "1 quadra" in msg or "uma quadra" in msg:
            updates["micro_location"] = {"value": "1_quadra", "status": "confirmed", "source": "user", "raw_text": message}
            return updates
        if "2" in msg or "3" in msg or "duas" in msg or "tres" in msg:
            updates["micro_location"] = {"value": "2-3_quadras", "status": "confirmed", "source": "user", "raw_text": message}
            return updates

    # NOVO: Leisure required
    if lk == "leisure_required":
        if is_yes:
            updates["leisure_required"] = {"value": "yes", "status": "confirmed", "source": "user", "raw_text": message}
            return updates
        if is_no:
            updates["leisure_required"] = {"value": "no", "status": "confirmed", "source": "user", "raw_text": message}
            return updates

    # NOVO: Leisure level
    if lk == "leisure_level":
        if "complet" in msg or "tudo" in msg:
            updates["leisure_level"] = {"value": "full", "status": "confirmed", "source": "user", "raw_text": message}
            return updates
        if "simples" in msg or "basico" in msg or "básico" in msg:
            updates["leisure_level"] = {"value": "simple", "status": "confirmed", "source": "user", "raw_text": message}
            return updates
        if "ok" in msg or "razoavel" in msg or "medio" in msg or "médio" in msg:
            updates["leisure_level"] = {"value": "ok", "status": "confirmed", "source": "user", "raw_text": message}
            return updates

    # NOVO: Floor preference
    if lk == "floor_pref":
        if "alto" in msg:
            updates["floor_pref"] = {"value": "alto", "status": "confirmed", "source": "user", "raw_text": message}
            return updates
        if "baixo" in msg:
            updates["floor_pref"] = {"value": "baixo", "status": "confirmed", "source": "user", "raw_text": message}
            return updates
        if "medio" in msg or "médio" in msg:
            updates["floor_pref"] = {"value": "medio", "status": "confirmed", "source": "user", "raw_text": message}
            return updates

    # NOVO: Sun preference
    if lk == "sun_pref":
        if "nascente" in msg or "manha" in msg or "manhã" in msg:
            updates["sun_pref"] = {"value": "nascente", "status": "confirmed", "source": "user", "raw_text": message}
            return updates
        if "poente" in msg or "tarde" in msg:
            updates["sun_pref"] = {"value": "poente", "status": "confirmed", "source": "user", "raw_text": message}
            return updates

    if lk == "lead_name":
        if msg:
            cleaned = msg
            for prefix in ["meu nome e", "meu nome é", "me chamo", "sou ", "nome ", "eu sou", "aqui é", "aqui e"]:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
            updates["lead_name"] = {"value": cleaned.strip().title(), "status": "confirmed", "source": "user", "raw_text": message}
            return updates

    if lk == "lead_phone":
        # Captura número de telefone — qualquer resposta que tenha dígitos suficientes
        digits = "".join(ch for ch in message if ch.isdigit())
        if len(digits) >= 8:
            updates["lead_phone"] = {"value": message.strip(), "status": "confirmed", "source": "user", "raw_text": message}
            return updates

    if lk in {"intent", "operation"}:
        if any(token in msg for token in {"comprar", "compra"}):
            updates["intent"] = {"value": "comprar", "status": "confirmed", "source": "user"}
            return updates
        if any(token in msg for token in {"alugar", "aluguel"}):
            updates["intent"] = {"value": "alugar", "status": "confirmed", "source": "user"}
            return updates
        if is_yes and state.intent:
            updates["intent"] = {"value": state.intent, "status": "confirmed", "source": "user"}
            return updates

    if lk == "intent_stage":
        stage = None
        inferred_timeline = None

        if any(token in msg for token in {"olhando", "pesquis", "só olhando", "so olhando", "curioso", "sem pressa"}):
            stage = "researching"
            # Pesquisando sem pressa → timeline mais longo (3-6 meses)
            inferred_timeline = "6m"
        elif any(token in msg for token in {"visita", "visitar", "marcar", "agendar", "agenda", "próximas semanas", "proximas semanas", "rápido", "rapido", "pronto", "urgente"}):
            stage = "ready_to_visit"
            # Pronto para visitar → timeline curto (30 dias)
            inferred_timeline = "30d"
        elif "negoci" in msg:
            stage = "negotiating"
            # Negociando → timeline imediato
            inferred_timeline = "30d"

        if stage:
            updates["intent_stage"] = {"value": stage, "status": "confirmed", "source": "user"}
            # Infere timeline baseado no intent_stage
            if inferred_timeline and not state.criteria.timeline:
                updates["timeline"] = {"value": inferred_timeline, "status": "inferred", "source": "intent_stage"}
            return updates

    return updates


def _avoid_repeat_question(state: SessionState, proposed_key: Optional[str]) -> Optional[str]:
    if not proposed_key:
        return proposed_key
    if proposed_key == "city" and not state.criteria.city:
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


def _prepend_greeting_if_needed(message: str, reply: str, state: SessionState = None) -> str:
    """
    Adiciona cumprimento ao início da resposta apenas no primeiro turno.

    Args:
        message: Mensagem do usuário
        reply: Resposta do bot
        state: Estado da sessão (para verificar se é primeiro turno)

    Returns:
        Resposta com ou sem cumprimento
    """
    # Só adiciona cumprimento no primeiro turno (evita "Bom dia!" no meio da conversa)
    if state and state.message_index > 1:
        return reply

    low = message.lower()
    if any(g in low for g in GREETINGS):
        if not reply.lower().startswith(("bom dia", "boa tarde", "boa noite", "oi", "olá", "ola")):
            if "tarde" in low:
                return "Boa tarde! " + reply
            elif "noite" in low:
                return "Boa noite! " + reply
            return "Bom dia! " + reply
    return reply


def _should_reset_session(state: SessionState, message: str) -> bool:
    low = message.lower()
    has_greeting = any(g in low for g in GREETINGS)
    has_intent_keyword = any(k in low for k in INTENT_KEYWORDS)
    completed = getattr(state, "completed", False)
    stale = (state.last_activity_at and (time.time() - state.last_activity_at) > 3 * 3600)
    return (completed and has_greeting and has_intent_keyword) or stale


def _is_valid_name(name: Optional[str]) -> bool:
    if not name:
        return False
    cleaned = str(name).strip().lower()
    if cleaned in GENERIC_NAMES or len(cleaned) < 3:
        return False
    return True


def _format_budget(value: int) -> str:
    """Formata valor monetário em PT-BR (ex: R$ 800.000)."""
    if value >= 1_000_000:
        # Formato milhões
        milhoes = value / 1_000_000
        if milhoes == int(milhoes):
            return f"R$ {int(milhoes)} milhão" if milhoes == 1 else f"R$ {int(milhoes)} milhões"
        else:
            return f"R$ {milhoes:.1f} milhões"
    else:
        # Formato com pontos
        return f"R$ {value:,.0f}".replace(",", ".")


def _format_budget_conflict_message(key: str, prev_val: Any, new_val: Any, state: SessionState) -> str:
    """
    Gera mensagem de conflito específica para budget, considerando ranges.
    """
    if key in {"budget", "budget_max"}:
        # Verificar se já existe budget_min definido
        budget_min = state.criteria.budget_min
        if budget_min and new_val and new_val < budget_min:
            # Conflito real: novo máximo é menor que o mínimo existente
            return (
                f"Aqui ficou registrado que seu orçamento mínimo é {_format_budget(budget_min)} "
                f"e máximo {_format_budget(prev_val)}. Agora você disse {_format_budget(new_val)}. "
                f"Isso fica fora da faixa. Pode confirmar qual é o orçamento correto?"
            )
        else:
            return (
                f"Aqui ficou registrado orçamento máximo de {_format_budget(prev_val)} "
                f"nesta conversa. Agora você disse {_format_budget(new_val)}. Qual vale?"
            )
    elif key == "budget_min":
        # Verificar se já existe budget_max definido
        budget_max = state.criteria.budget
        if budget_max and new_val and new_val > budget_max:
            # Conflito real: novo mínimo é maior que o máximo existente
            return (
                f"Aqui ficou registrado que seu orçamento máximo é {_format_budget(budget_max)} "
                f"e mínimo {_format_budget(prev_val)}. Agora você disse {_format_budget(new_val)}. "
                f"Isso fica fora da faixa. Pode confirmar qual é o orçamento correto?"
            )
        else:
            return (
                f"Aqui ficou registrado orçamento mínimo de {_format_budget(prev_val)} "
                f"nesta conversa. Agora você disse {_format_budget(new_val)}. Qual vale?"
            )
    else:
        # Conflito genérico (não-budget)
        return (
            f"Aqui ficou registrado {prev_val} nesta conversa. "
            f"Agora você disse {new_val}. Qual vale?"
        )


def handle_message(session_id: str, message: str, name: str | None = None, correlation_id: str | None = None) -> Dict[str, Any]:
    """
    Processa mensagem do cliente (máx 1 chamada LLM).
    """
    agent = get_agent()
    state = store.get(session_id)
    # Reset heurístico para nova conversa após conclusão
    if _should_reset_session(state, message):
        preserved_profile = state.lead_profile.copy()
        logger.info("SESSION_RESET reason=completed_or_stale correlation=%s", correlation_id)
        store.reset(session_id)
        state = store.get(session_id)
        state.lead_profile.update(preserved_profile)

    # Evita duplicar conclusão/persistência se já finalizado
    if state.completed:
        reply = "Seu perfil já foi registrado! Um corretor da Grankasa vai entrar em contato com você em breve 😊"
        return {"reply": reply, "state": state.to_public_dict()}

    # Controle de turnos/atividade
    state.set_current_turn(state.message_index + 1)
    triage_only = TRIAGE_ONLY

    low_msg = message.lower()
    if any(k in low_msg for k in ["baixar o preco", "baixar o preço", "desconto", "negociar", "negociação", "negociacao"]):
        return _human_handoff(state, reason="negociacao")

    if name and not state.lead_profile.get("name"):
        state.lead_profile["name"] = name
        state.lead_name = name

    state.history.append({"role": "user", "text": message})

    # Detecta confusão/pedido de esclarecimento ANTES de processar normalmente
    from .confusion_detector import (
        detect_confusion,
        generate_clarification_response,
        should_offer_options,
        format_options_message,
        is_answering_field
    )

    confusion_info = detect_confusion(message, state)

    # Se detectou confusão e temos um campo pendente
    if confusion_info and confusion_info.get("is_confused"):
        field = confusion_info.get("field")

        # Lê contador atual (já foi incrementado quando o bot fez a pergunta)
        if field:
            ask_count = state.field_ask_count.get(field, 0)

            # Se já tentou 3+ vezes (pergunta inicial + 2 confusões), oferece opções múltipla escolha
            should_offer, options = should_offer_options(field, ask_count)

            if should_offer and options:
                # Oferece opções estruturadas
                reply = format_options_message(field, options)
                state.awaiting_clarification = False  # Resetando após oferecer opções
                state.history.append({"role": "assistant", "text": reply})
                return {"reply": reply, "state": state.to_public_dict()}
            else:
                # Gera explicação do termo/campo
                explanation = generate_clarification_response(confusion_info, state)
                state.awaiting_clarification = True
                state.last_user_confusion_signal = message
                state.history.append({"role": "assistant", "text": explanation})
                return {"reply": explanation, "state": state.to_public_dict()}

    # Se estava aguardando clarificação e agora respondeu, limpa flag
    if state.awaiting_clarification:
        # Verifica se a resposta atual parece ser uma resposta válida ao campo
        if state.pending_field and is_answering_field(message, state.pending_field):
            state.awaiting_clarification = False
            state.last_user_confusion_signal = None

    # === EXTRACT-FIRST: Extraction sempre ocorre antes de decidir próxima ação ===
    # Isso garante que o state é atualizado mesmo se LLM falhar

    # 1. Heurística para respostas curtas (sim/não)
    user_short_updates = _short_reply_updates(message, state)

    # 2. Extração via regex (sempre determinístico)
    neighborhoods = tools.get_neighborhoods()
    extracted_updates = enrich_with_regex(message, state, {}, known_neighborhoods=neighborhoods)

    # 3. Override de intent se explícito
    low_msg = message.lower()
    override_phrase = "na verdade" in low_msg or "corrig" in low_msg
    override_intent = None
    if override_phrase:
        if "comprar" in low_msg:
            override_intent = "comprar"
        elif "alugar" in low_msg or "aluguel" in low_msg:
            override_intent = "alugar"

    # 4. Resolve cidade explícita
    explicit_city = resolve_city(message, state)
    if explicit_city:
        extracted_updates["city"] = {
            "value": explicit_city,
            "status": "override",
            "source": "user",
            "raw_text": message,
        }

    # 5. Merge updates: short replies
    if user_short_updates:
        extracted_updates.update(user_short_updates)

    # 6. Normaliza neighborhood
    if "neighborhood" in extracted_updates:
        nb = extracted_updates["neighborhood"]
        if isinstance(nb, dict):
            nb["status"] = "confirmed"
            nb["source"] = nb.get("source", "user")
            nb["raw_text"] = nb.get("raw_text") or message

    # 7. Aplica updates extraídos ANTES de chamar LLM
    conflicts, conflict_values = state.apply_updates(extracted_updates)

    # === DECISÃO (LLM ou fallback) ===
    # Agora que extraction já ocorreu, podemos decidir próxima ação
    try:
        decision, used_llm = agent.decide(message, state, neighborhoods, correlation_id=correlation_id)
    except Exception as llm_exc:
        # Importar LLMUnavailableError aqui para evitar circular import
        from .llm import LLMUnavailableError

        # Se LLM ficou indisponível (503/429/timeout), degraded mode foi ativado
        if isinstance(llm_exc, LLMUnavailableError):
            logger.warning("DEGRADED_MODE: LLM indisponível: %s. Usando fallback determinístico.", llm_exc.error_type)
            # state.llm_degraded já foi setado por llm_decide()
            # Usar fallback completo
            from .llm import _get_fallback_decision
            decision = _get_fallback_decision(message, agent._build_state_summary(state, neighborhoods), TRIAGE_ONLY)
            decision["degraded_mode"] = True
            decision["degraded_reason"] = llm_exc.error_type
            used_llm = False
        else:
            # Outro erro inesperado, re-raise
            raise

    new_intent = decision.get("intent")
    extracted = decision.get("criteria", {}) or {}
    # extracted_updates já foi aplicado acima (extract-first)
    # Merge com o que veio do LLM se houver novos
    llm_extracted_updates = decision.get("extracted_updates") or {k: {"value": v, "status": "confirmed"} for k, v in extracted.items()}
    if llm_extracted_updates:
        # Merge com os já extraídos (priorizar user-confirmed sobre LLM-inferred)
        for key, val in llm_extracted_updates.items():
            if key not in extracted_updates:
                extracted_updates[key] = val

    handoff_info = decision.get("handoff", {})
    plan_info = decision.get("plan", {})
    fallback_reason = decision.get("fallback_reason")
    degraded_mode = decision.get("degraded_mode", False)

    if fallback_reason:
        state.fallback_reason = fallback_reason

    # Atualiza/override intent
    if override_intent and state.intent and override_intent != state.intent:
        state.intent = override_intent
        logger.info("Intent overridden: %s", override_intent)
    if new_intent and not state.intent:
        state.intent = new_intent
        logger.info("Intent: %s", new_intent)

    if extracted:
        logger.debug("Critérios extraídos: %s", extracted)

    faq_intent = faq.detect_faq_intent(message)

    # Saída da Grankasa no primeiro turno: saudão pura (mensagem é só cumprimento, sem dado imobiliário)
    if state.message_index == 1 and not faq_intent:
        low = message.lower()
        keywords = {"comprar", "alugar", "ap", "apartamento", "casa", "bairro", "cidade", "visitar", "orc", "budget", "r$", "vaga", "quarto", "mil"}
        has_digits = any(ch.isdigit() for ch in low)
        criteria_empty = all(v is None for v in state.criteria.__dict__.values())
        is_pure_greeting = criteria_empty and not state.intent and not has_digits and not any(k in low for k in keywords)
        if is_pure_greeting:
            # Escolhe a saudão certa pelo horário da mensagem
            if "tarde" in low:
                greeting_reply = _GRANKASA_GREETING_TARDE
            elif "noite" in low:
                greeting_reply = _GRANKASA_GREETING_NOITE
            elif "dia" in low:
                greeting_reply = _GRANKASA_GREETING
            else:
                greeting_reply = _GRANKASA_GREETING_NEUTRAL
            state.last_question_key = "intent"
            state.pending_field = "intent"
            state.field_ask_count["intent"] = state.field_ask_count.get("intent", 0) + 1
            state.last_bot_utterance = greeting_reply
            if "intent" not in state.asked_questions:
                state.asked_questions.append("intent")
            state.history.append({"role": "assistant", "text": greeting_reply})
            return {"reply": greeting_reply, "state": state.to_public_dict()}

    # Aplica lead scoring a cada mensagem
    score = compute_lead_score(state)
    state.lead_score.temperature = score["temperature"]
    state.lead_score.score = score["score"]
    state.lead_score.reasons = score["reasons"]
    logger.info("LEAD_SCORE score=%s temp=%s reasons=%s correlation=%s", score['score'], score['temperature'], score['reasons'], correlation_id)

    # Aplica quality scoring
    quality = compute_quality_score(state)
    logger.info("QUALITY_SCORE score=%s grade=%s completeness=%s confidence=%s correlation=%s", quality['score'], quality['grade'], quality['completeness'], quality['confidence'], correlation_id)

    # Handoff (regras IA + decisão)
    if handoff_info.get("should"):
        reason = handoff_info.get("reason", "outro")
        logger.info("Handoff: %s", reason)
        return _human_handoff(state, reason=reason)

    # === TRIAGEM ONLY ===
    if triage_only:
        if conflicts:
            key = conflicts[0]
            vals = conflict_values.get(key, {})
            prev_val = vals.get("previous") if vals else state.triage_fields.get(key, {}).get("value")
            new_val = vals.get("new") if vals else extracted_updates.get(key, {}).get("value")

            # Usar mensagem formatada específica para budget ou genérica
            question = _format_budget_conflict_message(key, prev_val, new_val, state)

            state.last_question_key = key
            state.pending_field = key
            state.field_ask_count[key] = state.field_ask_count.get(key, 0) + 1
            state.last_bot_utterance = question
            if key not in state.asked_questions:
                state.asked_questions.append(key)
            state.history.append({"role": "assistant", "text": question})
            return {"reply": question, "state": state.to_public_dict()}

        # FAQ antes de seguir o funil
        faq_intent = faq.detect_faq_intent(message)
        if faq_intent:
            faq_reply = faq.answer_faq(faq_intent, state)
            missing = missing_critical_fields(state)
            if missing:
                next_key = next_best_question_key(state)
                next_key = _avoid_repeat_question(state, next_key)
                if next_key == "neighborhood" and not state.criteria.city:
                    next_key = "city"
                follow_up = _question_text_for_key(next_key, state)
                combined = f"{faq_reply}\n\nSó pra eu te ajudar melhor: {follow_up}"
                state.last_question_key = next_key
                state.pending_field = next_key
                state.field_ask_count[next_key] = state.field_ask_count.get(next_key, 0) + 1
                state.last_bot_utterance = combined
                if next_key and next_key not in state.asked_questions:
                    state.asked_questions.append(next_key)
                state.history.append({"role": "assistant", "text": combined})
                return {"reply": combined, "state": state.to_public_dict()}
            state.history.append({"role": "assistant", "text": faq_reply})
            return {"reply": faq_reply, "state": state.to_public_dict()}

        missing = missing_critical_fields(state)
        if missing:
            next_key = next_best_question_key(state)
            next_key = _avoid_repeat_question(state, next_key)
            if next_key == "neighborhood" and not state.criteria.city:
                next_key = "city"
            question = _question_text_for_key(next_key, state)
            state.last_question_key = next_key
            state.pending_field = next_key  # Rastreia campo sendo coletado
            state.field_ask_count[next_key] = state.field_ask_count.get(next_key, 0) + 1  # Incrementa contador
            state.last_bot_utterance = question  # Salva pergunta do bot
            if next_key and next_key not in state.asked_questions:
                state.asked_questions.append(next_key)

            reply = _prepend_greeting_if_needed(message, question, state)
            if state.fallback_reason:
                reply = f"Vou seguir no modo simples: {reply}"
            state.history.append({"role": "assistant", "text": reply})
            return {"reply": reply, "state": state.to_public_dict()}

        # === QUALITY GATE ===
        # Verifica se quality_score permite handoff
        from .quality_gate import should_handoff, next_question_from_quality_gaps, detect_field_refusal, mark_field_refusal

        quality = compute_quality_score(state)

        # Detectar recusa antes de aplicar gate
        if detect_field_refusal(message) and state.last_question_key:
            mark_field_refusal(state, state.last_question_key)

        if not should_handoff(state, quality):
            # Quality gate bloqueou handoff - fazer pergunta cirúrgica
            next_key = next_question_from_quality_gaps(state, quality)
            if next_key:
                state.quality_gate_turns += 1
                question = _question_text_for_key(next_key, state)
                state.last_question_key = next_key
                state.pending_field = next_key  # Rastreia campo sendo coletado
                state.field_ask_count[next_key] = state.field_ask_count.get(next_key, 0) + 1
                state.last_bot_utterance = question
                if next_key not in state.asked_questions:
                    state.asked_questions.append(next_key)

                # Contexto: avisar que está quase pronto mas falta um detalhe
                if state.quality_gate_turns == 1:
                    question = f"Quase lá! Só preciso de mais um detalhe: {question}"

                reply = _prepend_greeting_if_needed(message, question, state)
                state.history.append({"role": "assistant", "text": reply})
                logger.info("QUALITY_GATE pergunta de gap: %s (turn %d/3)", next_key, state.quality_gate_turns)
                return {"reply": reply, "state": state.to_public_dict()}
            else:
                # Sem perguntas disponíveis, permitir handoff mesmo com score baixo
                logger.info("QUALITY_GATE sem perguntas disponíveis, permitindo handoff com grade=%s", quality.get('grade'))

        # Triagem concluída (sem campos missing ou quality gate passou)
        # Roteamento automático de lead para corretor
        # 1. Pede nome se não tem
        if not _is_valid_name(state.lead_profile.get("name")):
            name_q = "Quase lá 😊 Antes de eu fechar seu perfil, pode me dizer seu nome?"
            state.last_question_key = "lead_name"
            state.pending_field = "lead_name"
            state.field_ask_count["lead_name"] = state.field_ask_count.get("lead_name", 0) + 1
            state.last_bot_utterance = name_q
            if "lead_name" not in state.asked_questions:
                state.asked_questions.append("lead_name")
            state.history.append({"role": "assistant", "text": name_q})
            return {"reply": name_q, "state": state.to_public_dict()}

        # 2. Pede telefone se não tem
        if not state.lead_profile.get("phone"):
            phone_q = "E pra o corretor conseguir te contatar, qual o seu celular ou WhatsApp?"
            state.last_question_key = "lead_phone"
            state.pending_field = "lead_phone"
            state.field_ask_count["lead_phone"] = state.field_ask_count.get("lead_phone", 0) + 1
            state.last_bot_utterance = phone_q
            if "lead_phone" not in state.asked_questions:
                state.asked_questions.append("lead_phone")
            state.history.append({"role": "assistant", "text": phone_q})
            return {"reply": phone_q, "state": state.to_public_dict()}

        # === SLA POLICY ===
        # Classificar lead e determinar ação SLA antes do roteamento
        from .sla import (
            classify_lead,
            compute_sla_action,
            should_emit_hot_event,
            build_hot_lead_event,
        )

        lead_score_value = state.lead_score.score
        lead_class = classify_lead(lead_score_value, state)
        quality = compute_quality_score(state)
        sla_action = compute_sla_action(lead_class, quality.get("grade"), state)

        # Atualizar estado com classificação SLA
        state.lead_class = lead_class
        state.sla = sla_action["sla_type"]

        logger.info("SLA lead_class=%s score=%s sla=%s priority=%s correlation=%s", lead_class, lead_score_value, state.sla, sla_action['priority'], correlation_id)

        # Roteamento (com priority se HOT)
        routing_result = route_lead(state, correlation_id=correlation_id, priority=sla_action["priority"])
        assigned_agent_info = None

        if routing_result:
            assigned_agent_info = {
                "id": routing_result.agent_id,
                "name": routing_result.agent_name,
                "whatsapp": routing_result.whatsapp if tools.EXPOSE_AGENT_CONTACT else None,
                "score": routing_result.score,
                "reasons": routing_result.reasons,
                "fallback": routing_result.fallback
            }

        # Gera summary com informação do corretor atribuído
        summary = build_summary_payload(state, assigned_agent=assigned_agent_info)
        summary["payload"]["lead_score"] = state.lead_score.__dict__
        summary["payload"]["quality_score"] = quality
        summary["payload"]["lead_class"] = lead_class
        summary["payload"]["sla"] = state.sla

        if assigned_agent_info:
            summary["payload"]["assigned_agent"] = assigned_agent_info
            summary["payload"]["routing"] = {
                "strategy": routing_result.strategy,
                "evaluated_agents_count": routing_result.evaluated_agents_count,
                "priority": sla_action["priority"]
            }

        state.completed = True
        persist_state(state)

        # Persistência pipeline expandida
        import uuid
        lead_id = uuid.uuid4().hex
        now_ts = time.time()
        completed_at = now_ts
        created_at = state.last_activity_at or now_ts
        lead_record = {
            "lead_id": lead_id,
            "session_id": state.session_id,
            "created_at": created_at,
            "completed_at": completed_at,
            "lead_profile": state.lead_profile,
            "criteria": state.criteria.__dict__,
            "triage_fields": state.triage_fields,
            "lead_score": state.lead_score.__dict__,
            "quality_score": quality,
            "assigned_agent": assigned_agent_info,
            "lead_class": lead_class,
            "sla": state.sla,
            "priority": sla_action["priority"],
            "last_action": f"{lead_class.lower()}_handoff",
            "flags": {
                "is_completed": True,
                "is_hot": lead_class == "HOT",
                "needs_followup": quality.get("grade") != "A",
                "llm_degraded": state.llm_degraded,  # Circuit breaker ativo durante sessão
            },
            "llm_status": {
                "degraded": state.llm_degraded,
                "last_error": state.llm_last_error,
                "degraded_until": state.llm_degraded_until_ts,
            } if state.llm_degraded else None,
        }
        persistence.append_lead(lead_record)
        if state.lead_profile.get("name"):
            persistence.update_lead_index(state.lead_profile["name"], lead_id)

        # Emitir evento HOT_LEAD com proteção contra duplicata
        if should_emit_hot_event(state, lead_class):
            event = build_hot_lead_event(
                lead_id=lead_id,
                session_state=state,
                lead_score=lead_score_value,
                quality_grade=quality.get("grade"),
                assigned_agent=assigned_agent_info,
                timestamp=completed_at
            )
            logger.info("NOTIFY HOT_LEAD lead_id=%s name=%s score=%s correlation=%s", lead_id, state.lead_profile.get('name'), lead_score_value, correlation_id)
            persistence.append_event(event)
            state.hot_lead_emitted = True

        # Mensagem final para o cliente: resumo humanizado completo (dados + contato fictício)
        # O summary["text"] já foi gerado por build_summary_payload com todos os dados
        reply = summary["text"]
        state.history.append({"role": "assistant", "text": reply})
        return {
            "reply": reply,
            "state": state.to_public_dict(),
            "summary": summary["payload"],
            "handoff": tools.handoff_human(str(summary["payload"]))
        }

    # FAQ para fluxo normal
    if faq_intent:
        faq_reply = faq.answer_faq(faq_intent, state)
        missing = missing_critical_fields(state)
        if missing:
            next_key = next_best_question_key(state)
            next_key = _avoid_repeat_question(state, next_key)
            if next_key == "neighborhood" and not state.criteria.city:
                next_key = "city"
            follow_up = _question_text_for_key(next_key, state)
            combined = f"{faq_reply}\n\nSó pra eu te ajudar melhor: {follow_up}"
            state.last_question_key = next_key
            if next_key and next_key not in state.asked_questions:
                state.asked_questions.append(next_key)
            state.history.append({"role": "assistant", "text": combined})
            return {"reply": combined, "state": state.to_public_dict()}
        state.history.append({"role": "assistant", "text": faq_reply})
        return {"reply": faq_reply, "state": state.to_public_dict()}

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

    logger.info("Plano: %s - %s", plan.action, plan.reasoning or plan.message[:50])

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
        if qkey == "neighborhood" and not state.criteria.city:
            qkey = "city"
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
