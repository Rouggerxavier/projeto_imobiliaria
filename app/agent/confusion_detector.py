"""
Confusion & Clarification Detection Module

Detecta quando o usuário está confuso, pedindo esclarecimento,
ou fazendo meta-perguntas sobre a pergunta do bot.
"""

from __future__ import annotations
import re
from typing import Optional, Dict, Any, Tuple
from .state import SessionState


# Padrões que indicam confusão ou pedido de esclarecimento
CONFUSION_PATTERNS = [
    # Perguntas diretas sobre termos
    r"\b(de que|do que|de qual|sobre o que)\b.*\?",
    r"\bcomo assim\b",
    r"\bo que (é|e|significa)\b",
    r"\bque significa\b",
    r"\bnão entendi\b",
    r"\bnao entendi\b",
    r"\bnão compreendi\b",
    r"\bconfuso\b",
    r"\bconfusa\b",

    # Repetição do termo com interrogação
    r"\b(\w+)\?\?+",  # "vagas??" "sondando??"

    # Perguntas echos (repete termo da pergunta anterior)
    r"\b(vagas|vaga)\s+(de\s+)?(que|carro|garagem)\?",
    r"\bsondando\?",
    r"\bprazo\?",
    r"\btipo\?",
    r"\bquartos\?",

    # Expressões de dúvida
    r"\bhã\?*",
    r"\beh\?+",
    r"\buhn\?",
    r"\bcomo\?",
    r"\bpor que\b.*\?",
    r"\bporque\b.*\?",

    # Pedidos explícitos de explicação
    r"\bexplica\b",
    r"\bme explica\b",
    r"\bpode explicar\b",
    r"\bo que você quer dizer\b",
    r"\bo que voce quer dizer\b",
]


# Termos específicos que indicam meta-pergunta (pergunta sobre a pergunta)
META_QUESTION_KEYWORDS = {
    "vagas", "vaga", "sondando", "prazo", "quartos", "suites",
    "tipo", "orçamento", "orcamento", "budget", "garagem"
}


def detect_confusion(message: str, state: SessionState) -> Optional[Dict[str, Any]]:
    """
    Detecta se a mensagem do usuário indica confusão ou pedido de esclarecimento.

    Args:
        message: Mensagem do usuário
        state: Estado da sessão

    Returns:
        Dict com informações sobre a confusão detectada, ou None se não houver confusão
        {
            "is_confused": bool,
            "type": "question_about_term" | "meta_question" | "general_confusion",
            "field": str (campo sobre o qual há confusão),
            "signal": str (padrão que gerou a detecção),
            "explanation_needed": bool
        }
    """
    msg_lower = message.lower().strip()

    # 1. Verifica padrões de confusão gerais
    for pattern in CONFUSION_PATTERNS:
        match = re.search(pattern, msg_lower)
        if match:
            return {
                "is_confused": True,
                "type": "general_confusion",
                "field": state.pending_field or state.last_question_key,
                "signal": match.group(0),
                "explanation_needed": True,
                "matched_pattern": pattern
            }

    # 2. Detecta meta-pergunta (pergunta sobre o termo da pergunta anterior)
    # Ex: Bot pergunta "Quantas vagas?" → Usuário: "vagas de carro?"
    if state.last_question_key and "?" in message:
        # Verifica se a mensagem contém o nome do campo sendo perguntado
        last_field = state.last_question_key

        # Mapping de campos para termos relacionados
        field_terms = {
            "parking": ["vagas", "vaga", "garagem", "estacionamento"],
            "bedrooms": ["quartos", "quarto"],
            "suites": ["suites", "suite", "suítes", "suíte"],
            "bathrooms_min": ["banheiros", "banheiro", "wc", "lavabo"],
            "property_type": ["tipo", "imovel", "imóvel"],
            "budget": ["orçamento", "orcamento", "preço", "preco", "valor"],
            "timeline": ["prazo", "tempo", "quando"],
            "intent_stage": ["sondando", "pesquisando", "visitando"],
            "micro_location": ["distancia", "distância", "praia", "quadras", "beira-mar", "orla"],
            "leisure_required": ["lazer", "area de lazer", "piscina", "academia"],
            "leisure_level": ["nivel", "nível", "completo", "simples"],
            "floor_pref": ["andar", "pavimento"],
            "sun_pref": ["sol", "nascente", "poente"],
        }

        # Verifica se algum termo relacionado ao campo aparece na pergunta
        related_terms = field_terms.get(last_field, [last_field])
        for term in related_terms:
            if term in msg_lower:
                return {
                    "is_confused": True,
                    "type": "meta_question",
                    "field": last_field,
                    "signal": message,
                    "explanation_needed": True,
                    "term_mentioned": term
                }

    # 3. Mensagem muito curta com apenas "?" pode indicar confusão
    if msg_lower in ["?", "??", "???", "hã?", "hã", "ahn?", "o que?"]:
        return {
            "is_confused": True,
            "type": "question_mark_only",
            "field": state.pending_field or state.last_question_key,
            "signal": message,
            "explanation_needed": True
        }

    return None


def is_answering_field(message: str, field: str) -> bool:
    """
    Verifica se a mensagem parece ser uma resposta válida ao campo,
    e não uma meta-pergunta sobre o campo.

    Args:
        message: Mensagem do usuário
        field: Campo sendo coletado

    Returns:
        True se parece ser uma resposta, False se parece ser pergunta/confusão
    """
    msg_lower = message.lower().strip()

    # Se tem ponto de interrogação, provavelmente é pergunta
    if "?" in message:
        return False

    # Padrões de resposta válida por campo
    answer_patterns = {
        "parking": r"^\d+$|^nenhuma?$|^zero$|^uma?$|^duas?$|^três|^tres|^1|^2|^3|tanto faz|indiferente",
        "bedrooms": r"^\d+$|^um$|^dois$|^três|^tres|^quatro|^1|^2|^3|^4",
        "suites": r"^\d+$|^nenhuma?$|^uma?$|^duas?$|^1|^2|^3|tanto faz|indiferente",
        "bathrooms_min": r"^\d+$|^um$|^dois$|^três|^tres|^1|^2|^3|tanto faz|indiferente",
        "micro_location": r"beira|quadra|praia|longe|tanto faz|indiferente",
        "leisure_required": r"\b(sim|não|nao|s|n|tanto faz|indiferente)\b",
        "leisure_level": r"(simples|completo|razoavel|ok|tanto faz|indiferente)",
        "floor_pref": r"(alto|baixo|medio|médio|tanto faz|indiferente)",
        "sun_pref": r"(nascente|poente|manha|manhã|tarde|tanto faz|indiferente)",
        "budget": r"\d{3,}|mil|milhão|milhao|k|mi",
        "intent": r"\b(comprar|alugar|compra|aluguel)\b",
        "city": r"\b(joão pessoa|joao pessoa|jp|campina|natal)\b",
        "property_type": r"\b(apartamento|casa|cobertura|apto|ap)\b",
    }

    pattern = answer_patterns.get(field)
    if pattern and re.search(pattern, msg_lower):
        return True

    # Se é muito curta e não tem padrão de resposta, assume que não é resposta
    if len(msg_lower) < 3:
        return False

    # Default: assume que é resposta se não detectou confusão
    return True


def generate_clarification_response(confusion_info: Dict[str, Any], state: SessionState) -> str:
    """
    Gera uma resposta de esclarecimento baseada no tipo de confusão detectada.

    Args:
        confusion_info: Informações sobre a confusão detectada
        state: Estado da sessão

    Returns:
        Mensagem de esclarecimento para o usuário
    """
    field = confusion_info.get("field")

    # Explicações por campo
    field_explanations = {
        "parking": (
            "Ah, desculpa a confusão! Estou perguntando sobre **vagas de garagem** "
            "(para estacionar carro). Quantas vagas de garagem você precisa? "
            "Pode ser 1, 2, 3 ou mais. Se não precisa de vaga, pode dizer 'nenhuma'."
        ),
        "bedrooms": (
            "Estou perguntando sobre a quantidade de **quartos** que você quer no imóvel. "
            "Por exemplo: 2 quartos, 3 quartos, 4 quartos... Quantos quartos você precisa?"
        ),
        "suites": (
            "Estou perguntando sobre **suítes** (quartos com banheiro privativo/próprio). "
            "Quantas suítes você gostaria? Pode ser 0 (nenhuma), 1, 2, 3... ou 'tanto faz' se não tiver preferência."
        ),
        "bathrooms_min": (
            "Estou perguntando sobre a quantidade **total de banheiros** no imóvel (incluindo os das suítes). "
            "Pode ser 1, 2, 3 ou mais. Se não faz diferença, pode dizer 'tanto faz'."
        ),
        "intent_stage": (
            "Estou perguntando se você está apenas **pesquisando opções** por enquanto, "
            "sem pressa, ou se já está **pronto(a) para agendar visitas** nos próximos dias. "
            "É só para eu entender sua urgência 😊"
        ),
        "budget": (
            "Estou perguntando sobre o **orçamento máximo** que você pode investir no imóvel. "
            "Pode ser um valor aproximado, tipo 'até 500 mil' ou 'entre 800 mil e 1 milhão'. "
            "Qual a faixa de preço que faz sentido pra você?"
        ),
        "timeline": (
            "Estou perguntando sobre o **prazo** em que você precisa do imóvel. "
            "É para já (30 dias)? Daqui a 3 meses? 6 meses? Ou sem pressa?"
        ),
        "micro_location": (
            "Estou perguntando sobre a **proximidade da praia**. Por exemplo: "
            "você prefere beira-mar (de frente pra praia), 1 quadra da praia, "
            "2-3 quadras, ou não importa a distância? Pode dizer 'tanto faz' se não tiver preferência."
        ),
        "leisure_required": (
            "Estou perguntando se você faz questão de **área de lazer** no condomínio "
            "(tipo piscina, academia, churrasqueira, etc.). Pode responder 'sim', 'não' ou 'tanto faz'."
        ),
        "leisure_level": (
            "Estou perguntando sobre o **nível de área de lazer** que você prefere:\n"
            "• **Simples**: só o básico (ex: piscina)\n"
            "• **Razoável**: algumas opções (piscina + academia)\n"
            "• **Completa**: tudo (piscina, academia, salão de festas, churrasqueira, etc.)\n"
            "Pode dizer 'tanto faz' se não tiver preferência específica."
        ),
        "floor_pref": (
            "Estou perguntando sobre a **preferência de andar**: você prefere andar baixo, médio, alto, "
            "ou tanto faz? Por exemplo, 'andar alto' tem mais vista, 'baixo' tem mais acesso fácil."
        ),
        "sun_pref": (
            "Estou perguntando sobre a **posição solar** do imóvel:\n"
            "• **Nascente**: sol da manhã\n"
            "• **Poente**: sol da tarde\n"
            "Pode dizer 'tanto faz' se não tiver preferência."
        ),
    }

    explanation = field_explanations.get(field)

    if explanation:
        return explanation

    # Explicação genérica se não tiver específica
    return (
        f"Desculpa, acho que não ficou claro! Estou perguntando sobre **{field}**. "
        "Pode reformular sua resposta? Se tiver alguma dúvida, é só perguntar que eu explico melhor 😊"
    )


def should_offer_options(field: str, ask_count: int) -> Tuple[bool, Optional[list]]:
    """
    Verifica se deve oferecer opções múltipla escolha para o campo,
    baseado no número de tentativas.

    Args:
        field: Campo sendo coletado
        ask_count: Número de vezes que o campo já foi perguntado

    Returns:
        (should_offer, options_list) onde:
        - should_offer: True se deve oferecer opções
        - options_list: Lista de opções a oferecer, ou None
    """
    # Só oferece opções após 3 tentativas (pergunta inicial + 2 confusões)
    if ask_count < 3:
        return False, None

    # Opções por campo
    field_options = {
        "parking": ["Nenhuma", "1 vaga", "2 vagas", "3 ou mais"],
        "bedrooms": ["1 quarto", "2 quartos", "3 quartos", "4 ou mais"],
        "suites": ["Nenhuma (0)", "1 suíte", "2 suítes", "3 ou mais", "Tanto faz"],
        "bathrooms_min": ["1 banheiro", "2 banheiros", "3 banheiros", "4 ou mais", "Tanto faz"],
        "micro_location": ["Beira-mar", "1 quadra da praia", "2-3 quadras", "Tanto faz"],
        "leisure_required": ["Sim, preciso", "Não preciso", "Tanto faz"],
        "leisure_level": ["Simples", "Razoável (ok)", "Completa", "Tanto faz"],
        "floor_pref": ["Andar baixo", "Andar médio", "Andar alto", "Tanto faz"],
        "sun_pref": ["Nascente (manhã)", "Poente (tarde)", "Tanto faz"],
        "property_type": ["Apartamento", "Casa", "Cobertura", "Outro"],
        "intent": ["Comprar", "Alugar"],
        "intent_stage": ["Só pesquisando", "Pronto para visitar"],
        "timeline": ["Até 30 dias", "Até 3 meses", "Até 6 meses", "Sem pressa"],
    }

    options = field_options.get(field)
    if options:
        return True, options

    return False, None


def format_options_message(field: str, options: list) -> str:
    """
    Formata mensagem com opções múltipla escolha.

    Args:
        field: Campo sendo coletado
        options: Lista de opções

    Returns:
        Mensagem formatada com as opções
    """
    field_labels = {
        "parking": "vagas de garagem",
        "bedrooms": "quartos",
        "suites": "suítes",
        "bathrooms_min": "banheiros",
        "micro_location": "proximidade da praia",
        "leisure_required": "área de lazer",
        "leisure_level": "nível de área de lazer",
        "floor_pref": "preferência de andar",
        "sun_pref": "posição solar",
        "property_type": "tipo de imóvel",
        "intent": "o que você quer",
        "intent_stage": "sua situação",
        "timeline": "prazo",
    }

    label = field_labels.get(field, field)

    options_text = "\n".join(f"• {opt}" for opt in options)

    return (
        f"Vejo que ficou confuso, vou facilitar! Sobre {label}, "
        f"qual dessas opções faz mais sentido pra você?\n\n"
        f"{options_text}\n\n"
        f"Pode escolher uma ou me dizer com suas palavras 😊"
    )
