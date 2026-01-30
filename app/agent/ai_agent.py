"""
Agente de IA Central - O Cérebro do Sistema

OTIMIZAÇÃO: Usa NO MÁXIMO 1 chamada LLM por mensagem via llm_decide()
Antes: 4 chamadas (intent, extraction, handoff, planning)
Agora: 1 chamada unificada OU fallback determinístico
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List, Tuple
from .llm import call_llm, call_llm_with_fallback, LLM_API_KEY, USE_LLM, llm_decide, TRIAGE_ONLY
from . import prompts
from .state import SessionState
from .rules import can_search_properties, missing_critical_fields


class RealEstateAIAgent:
    """
    Agente de IA especializado em atendimento imobiliário.

    OTIMIZAÇÃO: Usa NO MÁXIMO 1 chamada LLM por mensagem.

    Método principal: decide() - retorna intent, criteria, handoff, plan em 1 chamada
    """

    def __init__(self, use_llm: bool = True):
        """
        Args:
            use_llm: Se False, usa fallback de regras. True usa LLM.
        """
        self.use_llm = use_llm and USE_LLM and bool(LLM_API_KEY)
        if not self.use_llm:
            print("[WARN] Agente rodando em modo FALLBACK (sem LLM)")

    def decide(self, message: str, state: SessionState, neighborhoods: List[str] = None, correlation_id: str | None = None) -> Tuple[Dict[str, Any], bool]:
        """
        MÉTODO PRINCIPAL - Faz TUDO em 1 chamada LLM (ou fallback).

        Args:
            message: Mensagem do usuário
            state: Estado da sessão
            neighborhoods: Lista de bairros conhecidos

        Returns:
            (decision, used_llm)
            decision contém: intent, criteria, handoff, plan
        """
        # Prepara resumo compacto do estado
        state_summary = self._build_state_summary(state, neighborhoods or [])

        # Chama função unificada
        decision, used_llm = llm_decide(message, state_summary, use_cache=True, triage_only=TRIAGE_ONLY, correlation_id=correlation_id)

        if used_llm:
            print(f"[LLM] Decidiu: {decision.get('plan', {}).get('action', 'N/A')}")
        else:
            print(f"[FALLBACK] Decidiu: {decision.get('plan', {}).get('action', 'N/A')}")

        return decision, used_llm

    def _build_state_summary(self, state: SessionState, neighborhoods: List[str]) -> Dict[str, Any]:
        """Constrói resumo compacto do estado para a LLM."""
        missing = missing_critical_fields(state)
        can_search = can_search_properties(state)

        return {
            "intent": state.intent,
            "criteria": state.criteria.__dict__,
            "history": state.history[-6:],  # Últimas 6 mensagens
            "stage": state.stage,
            "last_suggestions": state.last_suggestions[:5] if state.last_suggestions else [],
            "missing_fields": missing,
            "can_search": can_search,
            "neighborhoods": neighborhoods[:20] if neighborhoods else [],  # Limita bairros
            "triage_fields": state.triage_fields,
            "asked_questions": state.asked_questions,
            "last_question_key": state.last_question_key,
            "completed": state.completed
        }
    
    def classify_intent(self, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Classifica a intenção do cliente usando LLM.
        
        Args:
            message: Mensagem do cliente
            context: Contexto adicional (histórico, estado)
            
        Returns:
            {
                "intent": "comprar|alugar|investir|pesquisar|vender|...",
                "confidence": 0.0-1.0,
                "reasoning": "explicação"
            }
        """
        if not self.use_llm:
            return self._classify_intent_fallback(message)
        
        payload = {
            "message": message,
            "context": context or {}
        }
        
        try:
            result = call_llm(
                system_prompt=prompts.INTENT_CLASSIFICATION_PROMPT,
                user_message=payload,
                temperature=0.2  # Baixa para ser mais determinístico
            )
            return result
        except Exception as e:
            print(f"⚠️ Erro na classificação de intent, usando fallback: {e}")
            return self._classify_intent_fallback(message)
    
    def extract_criteria(
        self,
        message: str,
        known_neighborhoods: List[str],
        current_criteria: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Extrai critérios de busca da mensagem usando LLM.
        
        Args:
            message: Mensagem do cliente
            known_neighborhoods: Lista de bairros conhecidos
            current_criteria: Critérios já coletados
            
        Returns:
            {
                "extracted": { "city": ..., "budget": ..., etc },
                "confidence": 0.0-1.0
            }
        """
        if not self.use_llm:
            return self._extract_criteria_fallback(message, known_neighborhoods)
        
        payload = {
            "message": message,
            "known_neighborhoods": known_neighborhoods[:20],  # Limita para não estourar tokens
            "current_criteria": current_criteria or {}
        }
        
        try:
            result = call_llm(
                system_prompt=prompts.EXTRACTION_PROMPT,
                user_message=payload,
                temperature=0.1  # Muito baixa para extração precisa
            )
            return result
        except Exception as e:
            print(f"⚠️ Erro na extração, usando fallback: {e}")
            return self._extract_criteria_fallback(message, known_neighborhoods)
    
    def plan_next_step(
        self,
        message: str,
        state: SessionState,
        extracted: Dict[str, Any],
        missing_fields: List[str],
        search_results: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Decide a próxima ação do agente usando LLM.
        
        Esta é a função MAIS IMPORTANTE - onde a IA decide o que fazer.
        
        Args:
            message: Última mensagem do cliente
            state: Estado completo da sessão
            extracted: Critérios extraídos da mensagem atual
            missing_fields: Campos ainda faltando
            search_results: Resultados de busca (se houver)
            
        Returns:
            {
                "action": "ASK|SEARCH|REFINE|ANSWER_GENERAL|SCHEDULE|HANDOFF|CLARIFY",
                "message": "resposta para o cliente",
                "question_key": "campo perguntado",
                "filters": {...},
                "handoff_reason": "motivo do handoff",
                "state_updates": {...}
            }
        """
        if not self.use_llm:
            return self._plan_fallback(state, missing_fields, extracted)
        
        # Prepara histórico de conversa para a LLM
        conversation_history = self._build_conversation_context(state)
        
        payload = {
            "current_message": message,
            "state": state.to_public_dict(),
            "extracted_from_message": extracted,
            "missing_critical_fields": missing_fields,
            "search_results_count": len(search_results) if search_results else 0,
            "conversation_turns": len(state.history)
        }
        
        try:
            result = call_llm(
                system_prompt=prompts.DIALOGUE_PLANNING_PROMPT,
                user_message=payload,
                temperature=0.4,  # Média para balancear criatividade e consistência
                conversation_history=conversation_history[-6:]  # Últimas 6 mensagens
            )
            return result
        except Exception as e:
            print(f"⚠️ Erro no planejamento, usando fallback: {e}")
            return self._plan_fallback(state, missing_fields, extracted)
    
    def should_handoff(
        self,
        message: str,
        state: SessionState,
        context: Optional[Dict] = None
    ) -> Tuple[bool, str, str]:
        """
        Decide se deve transferir para humano usando análise de IA.
        
        Args:
            message: Mensagem do cliente
            state: Estado da sessão
            context: Contexto adicional
            
        Returns:
            (should_handoff, reason, urgency)
        """
        if not self.use_llm:
            return self._handoff_fallback(message, state)
        
        payload = {
            "message": message,
            "conversation_history": [h["text"] for h in state.history[-5:]],
            "current_intent": state.intent,
            "criteria_collected": state.criteria.__dict__,
            "stage": state.stage,
            "context": context or {}
        }
        
        try:
            result = call_llm(
                system_prompt=prompts.HANDOFF_DECISION_PROMPT,
                user_message=payload,
                temperature=0.2
            )
            
            should = result.get("should_handoff", False)
            reason = result.get("reason", "outro")
            urgency = result.get("urgency", "media")
            
            return should, reason, urgency
        except Exception as e:
            print(f"⚠️ Erro na decisão de handoff, usando fallback: {e}")
            return self._handoff_fallback(message, state)
    
    def generate_natural_response(
        self,
        context: Dict[str, Any],
        properties: Optional[List[Dict]] = None
    ) -> str:
        """
        Gera uma resposta natural e contextualizada usando LLM.
        
        Use quando precisar de uma resposta mais elaborada/personalizada.
        
        Args:
            context: Contexto completo da conversa
            properties: Lista de imóveis (se relevante)
            
        Returns:
            Mensagem natural para o cliente
        """
        if not self.use_llm:
            return context.get("message", "Como posso ajudar?")
        
        payload = {
            "context": context,
            "properties": properties[:3] if properties else []  # Limita para não estourar tokens
        }
        
        try:
            result = call_llm(
                system_prompt=prompts.RESPONSE_GENERATION_PROMPT,
                user_message=payload,
                temperature=0.6  # Mais alta para respostas mais naturais
            )
            return result.get("message", context.get("message", "Como posso ajudar?"))
        except Exception:
            return context.get("message", "Como posso ajudar?")
    
    # ==================== FUNÇÕES DE FALLBACK (REGRAS) ====================
    # Estas funções são usadas quando a LLM não está disponível
    
    def _classify_intent_fallback(self, message: str) -> Dict[str, Any]:
        """Fallback baseado em keywords (código antigo)"""
        from .intent import classify_intent as old_classify
        intent = old_classify(message)
        return {
            "intent": intent or "outro",
            "confidence": 0.6 if intent else 0.3,
            "reasoning": f"Fallback: keyword match"
        }
    
    def _extract_criteria_fallback(self, message: str, neighborhoods: List[str]) -> Dict[str, Any]:
        """Fallback baseado em regex (código antigo)"""
        from .extractor import extract_criteria as old_extract
        extracted = old_extract(message, neighborhoods)
        return {
            "extracted": extracted,
            "confidence": 0.7
        }
    
    def _plan_fallback(
        self,
        state: SessionState,
        missing: List[str],
        extracted: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fallback com lógica de regras simples"""
        # Se não tem intenção, pergunta
        if not state.intent:
            city = extracted.get("city")
            msg = f"Bom dia! Você quer alugar ou comprar um imóvel em {city}?" if city else "Bom dia! Você quer alugar ou comprar?"
            return {
                "action": "ASK",
                "message": msg,
                "question_key": "intent",
                "reasoning": "Fallback: sem intenção"
            }
        
        # Se falta algo crítico, pergunta
        if missing:
            questions = {
                "location": "Qual cidade ou bairro você prefere?",
                "budget": "Qual o orçamento máximo? Pode ser aproximado.",
                "property_type": "Prefere apartamento, casa ou outro tipo?"
            }
            first_missing = missing[0]
            return {
                "action": "ASK",
                "message": questions.get(first_missing, "Pode me dar mais detalhes?"),
                "question_key": first_missing,
                "reasoning": f"Fallback: falta {first_missing}"
            }
        
        # Se tem tudo, busca
        return {
            "action": "SEARCH",
            "message": "Deixa eu buscar as melhores opções pra você.",
            "reasoning": "Fallback: tem critérios mínimos"
        }
    
    def _handoff_fallback(self, message: str, state: SessionState) -> Tuple[bool, str, str]:
        """Fallback para decisão de handoff baseado em keywords"""
        import unicodedata
        
        def strip_accents(text: str) -> str:
            return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        
        low = strip_accents(message.lower())
        
        # Keywords para diferentes motivos de handoff
        if any(k in low for k in ["humano", "atendente", "corretor", "pessoa"]):
            return True, "pedido_humano", "media"
        if any(k in low for k in ["desconto", "negociar", "baixar preco", "consegue baixar"]):
            return True, "negociacao", "alta"
        if any(k in low for k in ["visita", "visitar", "agendar", "marcar", "tour"]):
            return True, "visita", "alta"
        if any(k in low for k in ["reclamacao", "pessimo", "ruim", "horrivel"]):
            return True, "reclamacao", "alta"
        if any(k in low for k in ["contrato", "juridico", "advogado", "documentacao"]):
            return True, "juridico", "media"
        
        # Alta intenção
        if state.criteria.urgency == "alta" and state.criteria.budget:
            return True, "alta_intencao", "alta"
        
        return False, "", "baixa"
    
    def _build_conversation_context(self, state: SessionState) -> List[Dict[str, str]]:
        """
        Constrói contexto de conversa no formato esperado pela LLM.
        
        Returns:
            Lista de mensagens no formato [{"role": "user|assistant", "content": "..."}]
        """
        context = []
        for entry in state.history[-10:]:  # Últimas 10 mensagens
            role = "user" if entry.get("role") == "user" else "assistant"
            content = entry.get("text", "")
            if content:
                context.append({"role": role, "content": content})
        return context


# Instância global do agente
_agent_instance = None

def get_agent() -> RealEstateAIAgent:
    """Retorna instância singleton do agente de IA"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = RealEstateAIAgent(use_llm=True)
    return _agent_instance
