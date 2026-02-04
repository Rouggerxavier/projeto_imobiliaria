"""
Follow-up Automático - Nutrição de Leads

Sistema para identificar leads que precisam de follow-up e gerar
mensagens de qualificação adicionais (não venda).

Objetivo: Aumentar completude e confiança de leads warm/cold antes do handoff.
"""

from __future__ import annotations
import json
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Iterator
from pathlib import Path


# Lock para escrita atômica
_followup_lock = threading.Lock()

# Configuração
FOLLOWUP_META_PATH = os.getenv("FOLLOWUP_META_PATH", "data/followups.jsonl")


def load_leads(path: str = "data/leads.jsonl") -> Iterator[Dict[str, Any]]:
    """
    Carrega leads do arquivo JSONL.

    Args:
        path: Caminho para o arquivo de leads

    Yields:
        Dicionário com dados do lead
    """
    if not os.path.exists(path):
        print(f"[FOLLOWUP] Arquivo de leads não encontrado: {path}")
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lead = json.loads(line)
                        yield lead
                    except json.JSONDecodeError as e:
                        print(f"[FOLLOWUP] Erro ao parsear linha: {e}")
                        continue
    except Exception as e:
        print(f"[FOLLOWUP] Erro ao carregar leads: {e}")


def load_followup_history(path: str = None) -> Dict[str, List[str]]:
    """
    Carrega histórico de follow-ups enviados.

    Args:
        path: Caminho para arquivo de meta (default: FOLLOWUP_META_PATH)

    Returns:
        Dict {session_id: [followup_key1, followup_key2, ...]}
    """
    path = path or FOLLOWUP_META_PATH
    history: Dict[str, List[str]] = {}

    if not os.path.exists(path):
        return history

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        session_id = entry.get("session_id")
                        followup_key = entry.get("followup_key")
                        if session_id and followup_key:
                            if session_id not in history:
                                history[session_id] = []
                            history[session_id].append(followup_key)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"[FOLLOWUP] Erro ao carregar histórico: {e}")

    return history


def save_followup_sent(session_id: str, followup_key: str, path: str = None) -> None:
    """
    Registra que um follow-up foi enviado.

    Args:
        session_id: ID da sessão
        followup_key: Chave do follow-up enviado
        path: Caminho para arquivo de meta
    """
    path = path or FOLLOWUP_META_PATH

    entry = {
        "session_id": session_id,
        "followup_key": followup_key,
        "sent_at": datetime.utcnow().isoformat() + "Z"
    }

    with _followup_lock:
        try:
            # Garante que o diretório existe
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[FOLLOWUP] Erro ao salvar follow-up: {e}")


def should_followup(lead: Dict[str, Any], followup_history: Dict[str, List[str]]) -> bool:
    """
    Decide se um lead precisa de follow-up.

    Critérios:
    - Temperatura != "hot" OU quality_grade <= B
    - Lead parado (sem atividade recente)
    - Ainda não completou triagem OU tem gaps importantes
    - Não recebeu todos os follow-ups possíveis

    Args:
        lead: Dados do lead
        followup_history: Histórico de follow-ups enviados

    Returns:
        True se deve enviar follow-up
    """
    session_id = lead.get("session_id")
    if not session_id:
        return False

    # Já recebeu follow-ups?
    sent_followups = followup_history.get(session_id, [])

    # Verifica se completou
    completed = lead.get("completed", False)

    # Lead score
    lead_score = lead.get("lead_score", {})
    temperature = lead_score.get("temperature", "cold")

    # Quality score
    quality_score = lead.get("quality_score", {})
    grade = quality_score.get("grade", "D")

    # Timestamp (última atividade)
    timestamp = lead.get("timestamp", 0)
    now = datetime.utcnow().timestamp()
    hours_since = (now - timestamp) / 3600 if timestamp else 999

    # Regras de elegibilidade:

    # 1. Se hot e grade A, não precisa
    if temperature == "hot" and grade == "A":
        return False

    # 2. Se já completou, não precisa (handoff já foi feito)
    if completed:
        return False

    # 3. Deve estar parado há um tempo:
    # - Warm: >= 2 horas
    # - Cold: >= 24 horas
    min_idle_hours = 2 if temperature == "warm" else 24
    if hours_since < min_idle_hours:
        return False

    # 4. Não deve ter recebido muitos follow-ups (limite: 3)
    if len(sent_followups) >= 3:
        return False

    # Se passou pelas regras, precisa de follow-up
    return True


def next_followup_message(lead: Dict[str, Any], followup_history: Dict[str, List[str]]) -> Optional[Dict[str, Any]]:
    """
    Gera a próxima mensagem de follow-up para um lead.

    Estratégia:
    - Prioriza campos críticos faltantes
    - Depois campos dealbreakers (condo_max, payment_type, micro_location)
    - Mensagens curtas e focadas em qualificação (não venda)

    Args:
        lead: Dados do lead
        followup_history: Histórico de follow-ups

    Returns:
        {
            "message_text": str,
            "followup_key": str,
            "reasons": List[str]
        }
        ou None se não há follow-up aplicável
    """
    session_id = lead.get("session_id")
    sent_followups = followup_history.get(session_id, [])

    triage_fields = lead.get("triage_fields", {})
    intent = lead.get("intent")

    reasons = []

    # === CAMPOS CRÍTICOS FALTANTES ===

    # Neighborhood ausente
    neighborhood = triage_fields.get("neighborhood", {}).get("value")
    if not neighborhood and "neighborhood" not in sent_followups:
        return {
            "message_text": (
                "Oi! Pra eu não te mandar coisa fora do perfil, "
                "me diz: qual bairro você prefere? Pode citar 1-3 opções."
            ),
            "followup_key": "neighborhood",
            "reasons": ["missing_neighborhood"]
        }

    # Timeline ausente/ambíguo
    timeline = triage_fields.get("timeline", {}).get("value")
    if not timeline and "timeline" not in sent_followups:
        return {
            "message_text": (
                "Só pra eu alinhar: qual o prazo você trabalha? "
                "Até 30 dias, 3 meses, 6 meses, 12 meses ou flexível?"
            ),
            "followup_key": "timeline",
            "reasons": ["missing_timeline"]
        }

    # === DEALBREAKERS ===

    # Condomínio máximo (para budget alto)
    budget = triage_fields.get("budget", {}).get("value")
    condo_max = triage_fields.get("condo_max", {}).get("value")
    if budget and budget > 500000 and not condo_max and "condo_max" not in sent_followups:
        return {
            "message_text": (
                "Me diz uma coisa: você tem algum teto de condomínio mensal que não pode passar?"
            ),
            "followup_key": "condo_max",
            "reasons": ["missing_condo_max_high_budget"]
        }

    # Forma de pagamento (para compra)
    if intent == "comprar":
        payment_type = triage_fields.get("payment_type", {}).get("value")
        if not payment_type and "payment_type" not in sent_followups:
            return {
                "message_text": (
                    "Como você pretende pagar: financiamento, à vista, FGTS ou misto?"
                ),
                "followup_key": "payment_type",
                "reasons": ["missing_payment_type"]
            }

    # Micro-location ambígua (orla)
    micro_loc = triage_fields.get("micro_location", {})
    micro_val = micro_loc.get("value")
    micro_status = micro_loc.get("status")
    if (micro_val == "orla" or micro_status == "inferred") and "micro_location" not in sent_followups:
        return {
            "message_text": (
                "Sobre a distância da praia: você quer beira-mar, "
                "a 1 quadra ou 2-3 quadras da praia?"
            ),
            "followup_key": "micro_location",
            "reasons": ["micro_location_ambiguous"]
        }

    # === SUGESTÃO DE BAIRROS (se neighborhood ausente e já tentou antes) ===
    if not neighborhood and "neighborhood_suggest" not in sent_followups and "neighborhood" in sent_followups:
        return {
            "message_text": (
                "Pensando em João Pessoa: Manaíra, Tambaú ou Cabo Branco te interessam? "
                "Ou prefere outro bairro?"
            ),
            "followup_key": "neighborhood_suggest",
            "reasons": ["neighborhood_retry_with_suggestions"]
        }

    # Sem follow-up aplicável
    return None


def find_leads_for_followup(
    leads_path: str = "data/leads.jsonl",
    followup_meta_path: str = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Encontra leads que precisam de follow-up.

    Args:
        leads_path: Caminho para arquivo de leads
        followup_meta_path: Caminho para meta de follow-ups
        limit: Número máximo de leads a retornar

    Returns:
        Lista de dicts com lead + mensagem de follow-up
    """
    followup_history = load_followup_history(followup_meta_path)
    candidates = []

    for lead in load_leads(leads_path):
        if len(candidates) >= limit:
            break

        if should_followup(lead, followup_history):
            followup_msg = next_followup_message(lead, followup_history)
            if followup_msg:
                candidates.append({
                    "lead": lead,
                    "followup": followup_msg
                })

    return candidates
