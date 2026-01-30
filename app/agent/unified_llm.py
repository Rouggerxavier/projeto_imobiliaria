"""
Unified LLM Decision - UMA única chamada que retorna tudo
Reduz de 4 chamadas para 1 por mensagem
"""

from __future__ import annotations
import os
from typing import Dict, Any, Optional
from .llm import call_llm, GROQ_API_KEY
from .state import SessionState

# Flag global para controlar uso de LLM
USE_LLM = os.getenv("USE_LLM", "true").lower() == "true"

# Prompt CURTO e otimizado
UNIFIED_PROMPT = """Você é assistente imobiliário. Analise a mensagem e retorne JSON:
{
  "intent": "alugar|comprar|investir|pesquisar|vender|informacao_geral|suporte|humano|outro",
  "confidence": 0.0-1.0,
  "criteria": {
    "city": "ou null",
    "neighborhood": "ou null",
    "property_type": "apartamento|casa|studio|kitnet|cobertura|terreno|qualquer ou null",
    "bedrooms": número ou null,
    "parking": número ou null,
    "budget": número ou null,
    "pet": true/false/null,
    "furnished": true/false/null,
    "urgency": "alta|media|baixa ou null"
  },
  "criteria_status": {
    "campo": "confirmed|inferred"
  },
  "handoff": {
    "should": true/false,
    "reason": "negociacao|visita|pedido_humano|reclamacao|juridico|alta_intencao|outro",
    "urgency": "baixa|media|alta"
  },
  "plan": {
    "action": "ASK|SEARCH|REFINE|ANSWER_GENERAL|SCHEDULE|HANDOFF|CLARIFY",
    "message": "resposta ao cliente (2-3 frases, WhatsApp)",
    "question_key": "intent|location|budget|property_type|outros|null"
  }
}

REGRAS:
- criteria_status: "confirmed" se usuário disse, "inferred" se você assumiu
- handoff.should=true apenas se: negociação, visita, urgente, reclamação, jurídico, pede humano
- plan.action=SEARCH apenas se tem: intent (comprar/alugar) + location + budget + property_type
- plan.action=ASK se faltar dado crítico
- NÃO invente preços ou dados de imóveis
- Mensagens curtas (WhatsApp)
"""


def llm_decide(
    message: str,
    state: SessionState,
    missing_fields: list[str]
) -> Dict[str, Any]:
    """
    UMA única chamada LLM que retorna TUDO.
    
    Returns:
        {
            "intent": str,
            "confidence": float,
            "criteria": dict,
            "criteria_status": dict,
            "handoff": dict,
            "plan": dict
        }
    """
    
    # Contexto MÍNIMO (reduzir tokens)
    payload = {
        "message": message,
        "history": [h["text"] for h in state.history[-6:]],  # últimas 6
        "current_intent": state.intent,
        "confirmed_criteria": state.get_confirmed_criteria(),
        "missing_fields": missing_fields,
        "stage": state.stage
    }
    
    try:
        result = call_llm(
            system_prompt=UNIFIED_PROMPT,
            user_message=payload,
            temperature=0.3,
            timeout=20,  # mais curto
            max_retries=1  # só 1 retry
        )
        return result
    except Exception as e:
        # Se falhar, retorna estrutura vazia para fallback
        error_msg = str(e)
        if "429" in error_msg or "rate_limit" in error_msg.lower():
            print(f"⚠️ Rate limit atingido, usando fallback total")
        else:
            print(f"⚠️ LLM falhou: {e}, usando fallback")
        
        return {
            "intent": None,
            "confidence": 0.0,
            "criteria": {},
            "criteria_status": {},
            "handoff": {"should": False, "reason": "", "urgency": "baixa"},
            "plan": {"action": "ASK", "message": "", "question_key": None}
        }
