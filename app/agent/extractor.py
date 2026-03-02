from __future__ import annotations
import re
import unicodedata
from typing import Dict, Iterable, Optional, Set, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .state import SessionState


def _strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


PROPERTY_TYPES = {
    "apartamento": ["apto", "ape", "apartamento", "ap"],
    "casa": ["casa", "sobrado"],
    "cobertura": ["cobertura"],
    "studio": ["studio", "st"],
    "flat": ["flat"],
    "kitnet": ["kitnet", "kitinete", "kit"],
    "terreno": ["terreno", "lote"],
}

CITY_ALIASES = {
    "joao pessoa": "Joao Pessoa",
    "jp": "Joao Pessoa",
    "campina grande": "Campina Grande",
    "recife": "Recife",
    "natal": "Natal",
    "cabedelo": "Cabedelo",
}


def _parse_currency(fragment: str, suffix: Optional[str]) -> int:
    """
    Parse currency value with smart decimal/thousands separator detection.

    Examples:
        "1.200.000" -> 1200000 (thousands separator)
        "1.2" -> 1.2 (decimal)
        "1,2" -> 1.2 (decimal PT-BR)
        "11" -> 11
    """
    # Detectar se ponto é decimal ou separador de milhar
    dot_count = fragment.count(".")
    comma_count = fragment.count(",")

    if dot_count > 1:
        # Múltiplos pontos = separador de milhar (1.200.000)
        fragment = fragment.replace(".", "").replace(",", ".")
    elif dot_count == 1 and comma_count == 0:
        # Um ponto e nenhuma vírgula
        parts = fragment.split(".")
        if len(parts[1]) == 3:
            # Formato 1.200 (milhar) ou 1.200.000
            # Se tem exatamente 3 dígitos após o ponto, pode ser milhar
            # Mas se tem sufixo (mil, milhão), é provavelmente decimal (1.2 milhão)
            if suffix and suffix.lower() in {"mi", "milhao", "milhoes", "mil", "k", "m"}:
                # É decimal: 1.2 milhão
                fragment = fragment.replace(",", ".")
            else:
                # É separador de milhar: 1.200
                fragment = fragment.replace(".", "")
        else:
            # 1-2 dígitos após o ponto = decimal (1.1, 1.12)
            fragment = fragment.replace(",", ".")
    elif comma_count > 0:
        # Vírgula = decimal PT-BR
        fragment = fragment.replace(".", "").replace(",", ".")
    # else: sem pontos nem vírgulas, usar como está

    try:
        base = float(fragment)
    except ValueError:
        return 0

    mult = 1
    if suffix:
        suf = suffix.lower()
        if suf in {"mi", "milhao", "milhoes", "m"}:
            mult = 1_000_000
        elif suf in {"mil", "k"}:
            mult = 1_000

    return int(base * mult)


def _parse_budget_value(text: str) -> Optional[int]:
    """
    Parse um valor monetário isolado com melhor suporte para PT-BR.
    Ex: "1 milhão e 200 mil", "1.2 milhões", "900k", "R$ 800.000"
    """
    lowered = _strip_accents(text.lower()).strip()

    # Padrão "X milhão/milhões e Y mil" (ex: "1 milhão e 200 mil" = 1.200.000)
    complex_pattern = r"(\d+(?:[\.,]\d+)?)\s*(?:mi|milhao|milhoes|m)\s*(?:e)?\s*(\d+)\s*mil"
    m = re.search(complex_pattern, lowered)
    if m:
        milhoes = float(m.group(1).replace(",", "."))
        mil = float(m.group(2))
        return int(milhoes * 1_000_000 + mil * 1_000)

    # Padrão simples: número + sufixo
    simple_patterns = [
        r"r\$\s*(\d+)\.(\d{3})\.(\d{3})",  # R$ 1.200.000
        r"(\d+(?:[\.,]\d+)?)\s*(mi|milhao|milhoes|m|mil|k)\b",  # 1.2 milhão, 900k
    ]

    for pattern in simple_patterns:
        m = re.search(pattern, lowered)
        if m:
            if len(m.groups()) == 3:  # R$ X.XXX.XXX
                return int(m.group(1) + m.group(2) + m.group(3))
            else:
                return _parse_currency(m.group(1), m.group(2))

    return None


def parse_budget_range(text: str) -> Dict[str, Any]:
    """
    Extrai orçamento, detectando ranges (ex: "entre 800 mil e 1.2 milhão").

    Returns:
        {
            "budget_min": Optional[int],
            "budget_max": Optional[int],
            "is_range": bool,
            "raw_matches": List[int]
        }
    """
    lowered = _strip_accents(text.lower())

    # Padrões de range explícitos - capturar tudo entre os delimitadores
    # Ordem dos sufixos: mais longos primeiro para evitar match parcial
    suffix_pattern = r"(?:milhoes|milhao|mil|mi|m|k)"

    range_patterns = [
        # "entre X [sufixo] (e|a|ate) Y [sufixo com possível 'e Z mil']"
        rf"(?:entre|de)\s+([\d\.,]+\s*{suffix_pattern}?)\s+(?:e|a|ate|até)\s+([\d\.,]+\s*{suffix_pattern}?(?:\s+e\s+\d+\s+mil)?)",
        # "X [sufixo] até/ate Y [sufixo]" (pattern separado para pegar "X até Y")
        rf"([\d\.,]+\s*{suffix_pattern}?)\s+(?:ate|até)\s+([\d\.,]+\s*{suffix_pattern}?(?:\s+e\s+\d+\s+mil)?)",
        # "X [sufixo] a Y [sufixo]" (sem "entre" ou "de")
        rf"([\d\.,]+\s*{suffix_pattern})\s+a\s+([\d\.,]+\s*{suffix_pattern}?(?:\s+e\s+\d+\s+mil)?)",
        # "X [sufixo] - Y [sufixo]" ou "X~Y"
        rf"([\d\.,]+\s*{suffix_pattern}?)\s*[-~]\s+([\d\.,]+\s*{suffix_pattern}?(?:\s+e\s+\d+\s+mil)?)",
    ]

    for pattern in range_patterns:
        m = re.search(pattern, lowered, re.IGNORECASE)
        if m:
            val1 = _parse_budget_value(m.group(1))
            val2 = _parse_budget_value(m.group(2))
            if val1 and val2 and val1 > 0 and val2 > 0:
                # Garantir ordem crescente
                budget_min = min(val1, val2)
                budget_max = max(val1, val2)
                return {
                    "budget_min": budget_min,
                    "budget_max": budget_max,
                    "is_range": True,
                    "raw_matches": [val1, val2]
                }

    # Coletar todos os valores monetários PRIMEIRO
    all_values = []

    # Encontrar todos os valores monetários no texto (ordem correta de sufixos)
    for m in re.finditer(rf"([\d\.,]+)\s*({suffix_pattern})\b", lowered, re.IGNORECASE):
        value = _parse_currency(m.group(1), m.group(2))
        if value > 0:
            all_values.append(value)

    # R$ X.XXX.XXX
    for m in re.finditer(r"r\$\s*(\d+)\.(\d{3})\.(\d{3})", lowered):
        value = int(m.group(1) + m.group(2) + m.group(3))
        all_values.append(value)

    # Se encontrou múltiplos valores, verificar contexto
    if len(all_values) >= 2:
        # Pegar os 2 valores mais distintos
        unique_vals = sorted(set(all_values))
        if len(unique_vals) >= 2:
            # Range implícito detectado
            return {
                "budget_min": unique_vals[0],
                "budget_max": unique_vals[-1],
                "is_range": True,
                "raw_matches": unique_vals
            }

    # Se encontrou apenas 1 valor, verificar contexto (max-only vs min-only)
    if len(all_values) == 1:
        # Padrão "até X" / "máximo X" (apenas max)
        max_patterns = [
            rf"(?:ate|até|teto|maximo|max|limite)\s+(?:de\s+)?([\d\.,]+\s*{suffix_pattern}?(?:\s+e\s+\d+\s+mil)?)",
            rf"(?:por mes|mensal|no max|no maximo)\s+(?:de\s+)?([\d\.,]+\s*{suffix_pattern}?)",
        ]
        for pattern in max_patterns:
            if re.search(pattern, lowered, re.IGNORECASE):
                return {
                    "budget_min": None,
                    "budget_max": all_values[0],
                    "is_range": False,
                    "raw_matches": all_values
                }

        # Padrão "a partir de X" / "mínimo X" (apenas min)
        min_patterns = [
            rf"(?:a partir de|partir de|minimo|min|pelo menos)\s+([\d\.,]+\s*{suffix_pattern}?(?:\s+e\s+\d+\s+mil)?)",
        ]
        for pattern in min_patterns:
            if re.search(pattern, lowered, re.IGNORECASE):
                return {
                    "budget_min": all_values[0],
                    "budget_max": None,
                    "is_range": False,
                    "raw_matches": all_values
                }

        # Sem contexto específico, assumir budget_max (comportamento legado)
        return {
            "budget_min": None,
            "budget_max": all_values[0],
            "is_range": False,
            "raw_matches": all_values
        }

    # Nenhum valor encontrado
    return {
        "budget_min": None,
        "budget_max": None,
        "is_range": False,
        "raw_matches": []
    }


def extract_budget(text: str) -> Optional[int]:
    """
    Função legada para compatibilidade. Retorna apenas budget_max.
    Use parse_budget_range() para suporte completo a ranges.
    """
    result = parse_budget_range(text)
    return result.get("budget_max")


def extract_number(text: str, pattern: str) -> Optional[int]:
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def detect_type(text: str) -> Optional[str]:
    lowered = _strip_accents(text.lower())
    for canonical, aliases in PROPERTY_TYPES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}s?\b", lowered):
                return canonical
    if "qualquer" in lowered or "tanto faz" in lowered:
        return "qualquer"
    return None


def detect_city(text: str) -> Optional[str]:
    normalized = _strip_accents(text.lower())
    for alias, canonical in CITY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return canonical
    return None


def resolve_city(user_text: str, session_state: "SessionState") -> Optional[str]:
    """
    Detecta cidade explicitamente mencionada pelo usuário.
    Não aplica fallback automático.
    """
    _ = session_state  # reservado para regras futuras
    return detect_city(user_text)


def detect_neighborhood(text: str, known: Iterable[str]) -> Optional[str]:
    normalized = _strip_accents(text.lower())
    for bairro in known:
        if bairro and _strip_accents(bairro.lower()) in normalized:
            return bairro
    return None


def extract_boolean(text: str, keywords_true: Set[str], keywords_false: Set[str]) -> Optional[bool]:
    lowered = _strip_accents(text.lower())
    if any(k in lowered for k in keywords_true):
        return True
    if any(k in lowered for k in keywords_false):
        return False
    return None


def detect_indifferent(text: str) -> bool:
    """Detecta se a mensagem indica 'indiferente/tanto faz'."""
    lowered = _strip_accents(text.lower())
    indifferent_keywords = [
        "tanto faz", "indiferente", "qualquer", "nao importa", "não importa",
        "sem preferencia", "sem preferência", "pode ser qualquer"
    ]
    return any(kw in lowered for kw in indifferent_keywords)


def extract_bathrooms(text: str) -> Optional[int]:
    """Extrai quantidade de banheiros."""
    lowered = _strip_accents(text.lower())
    # Padrões: "2 banheiros", "1 banheiro", "3+ banheiros"
    match = extract_number(lowered, r"(\d+)\s*\+?\s*(banheiro|wc|lavabo|bath)s?")
    return match


def extract_beach_proximity(text: str) -> Optional[str]:
    """Extrai proximidade da praia."""
    lowered = _strip_accents(text.lower())
    if "beira mar" in lowered or "beira-mar" in lowered or "de frente" in lowered or "frente pra praia" in lowered:
        return "beira-mar"
    if "1 quadra" in lowered or "uma quadra" in lowered:
        return "1_quadra"
    if ("2 quadra" in lowered or "3 quadra" in lowered or "duas quadras" in lowered or
        "tres quadras" in lowered or "2-3 quadras" in lowered):
        return "2-3_quadras"
    if "longe da praia" in lowered or "afastado da praia" in lowered:
        return ">3_quadras"
    if "praia" in lowered or "orla" in lowered:
        return "orla"  # ambíguo, precisa esclarecimento
    return None


def extract_leisure_level(text: str) -> Optional[str]:
    """Extrai nível de área de lazer."""
    lowered = _strip_accents(text.lower())
    if "lazer complet" in lowered or "area completa" in lowered or "com tudo" in lowered:
        return "full"
    if "lazer ok" in lowered or "razoavel" in lowered or "medio" in lowered or "moderado" in lowered:
        return "ok"
    if "lazer simples" in lowered or "basico" in lowered or "minimo" in lowered:
        return "simple"
    return None


def extract_floor_preference(text: str) -> Optional[str]:
    """Extrai preferência de andar."""
    lowered = _strip_accents(text.lower())
    if "andar alto" in lowered or "ultimo andar" in lowered or "cobertura" in lowered:
        return "alto"
    if "andar medio" in lowered or "intermediario" in lowered:
        return "medio"
    if "andar baixo" in lowered or "terreo" in lowered or "primeiro andar" in lowered:
        return "baixo"
    return None


def extract_sun_preference(text: str) -> Optional[str]:
    """Extrai preferência de posição solar."""
    lowered = _strip_accents(text.lower())
    if "nascente" in lowered or "sol da manha" in lowered or "manha" in lowered:
        return "nascente"
    if "poente" in lowered or "sol da tarde" in lowered or "tarde" in lowered:
        return "poente"
    return None


def extract_criteria(message: str, known_neighborhoods: Iterable[str]) -> Dict[str, object]:
    text = message
    result: Dict[str, object] = {}

    lowered_plain = _strip_accents(text.lower())

    # Detecta "indiferente" global (aplicável a qualquer pergunta)
    is_indifferent = detect_indifferent(text)

    # Intent explícita (comprar/alugar)
    if "comprar" in lowered_plain or "compra" in lowered_plain or "investir" in lowered_plain:
        result["intent"] = "comprar"
    elif "alugar" in lowered_plain or "aluguel" in lowered_plain:
        result["intent"] = "alugar"

    city = detect_city(text)
    if city:
        result["city"] = city
    neighborhood = detect_neighborhood(text, known_neighborhoods)
    if neighborhood:
        result["neighborhood"] = neighborhood

    # Beach proximity (micro_location)
    beach_prox = extract_beach_proximity(text)
    if beach_prox:
        result["micro_location"] = beach_prox
    elif is_indifferent:
        result["micro_location"] = "indifferent"

    prop_type = detect_type(text)
    if prop_type:
        result["property_type"] = prop_type

    lowered = _strip_accents(text.lower())
    bedrooms = extract_number(lowered, r"(\d+)\s*(quarto|qtos|dorm|q\b|qts)")
    if bedrooms:
        result["bedrooms"] = bedrooms

    # Suítes
    suites = extract_number(lowered, r"(\d+)\s*(suite|su[ií]te)s?")
    if suites is not None:
        result["suites"] = suites
    elif "nenhuma suite" in lowered or "sem suite" in lowered or "0 suite" in lowered:
        result["suites"] = 0
    elif is_indifferent:
        result["suites"] = "indifferent"

    # Banheiros
    bathrooms = extract_bathrooms(text)
    if bathrooms is not None:
        result["bathrooms_min"] = bathrooms
    elif is_indifferent:
        result["bathrooms_min"] = "indifferent"

    parking = extract_number(lowered, r"(\d+)\s*(vaga|vagas)")
    if parking is not None:
        result["parking"] = parking

    budget_info = parse_budget_range(message)
    if budget_info.get("budget_min"):
        result["budget_min"] = budget_info["budget_min"]
    if budget_info.get("budget_max"):
        result["budget"] = budget_info["budget_max"]
    if budget_info.get("is_range"):
        result["budget_is_range"] = True

    pet = extract_boolean(text, {"pet", "cachorro", "gato", "aceita pet", "pet friendly"}, {"nao aceita pet", "sem pet"})
    if pet is not None:
        result["pet"] = pet
    elif is_indifferent:
        result["pet"] = "indifferent"

    furnished = extract_boolean(text, {"mobiliado", "mobiliada", "moveis", "mobilia"}, {"sem mobilia", "nao mobiliado"})
    if furnished is not None:
        result["furnished"] = furnished
    elif is_indifferent:
        result["furnished"] = "indifferent"

    urgency = None
    if any(k in lowered for k in ["urgente", "hoje", "agora", "esse mes", "o quanto antes"]):
        urgency = "alta"
    elif any(k in lowered for k in ["proximo mes", "duas semanas", "em breve"]):
        urgency = "media"
    if urgency:
        result["urgency"] = urgency

    if "o mais rapido" in lowered or "o mais rápido" in lowered or "mais rapido possivel" in lowered or "o quanto antes" in lowered or "asap" in lowered:
        result["timeline"] = "3m"

    # Leisure detection
    leisure_level = extract_leisure_level(text)
    if leisure_level:
        result["leisure_level"] = leisure_level

    # Leisure required
    if "area de lazer" in lowered or "lazer" in lowered:
        if "nao" in lowered or "não" in lowered or "sem lazer" in lowered:
            result["leisure_required"] = "no"
        elif "preciso" in lowered or "importante" in lowered or "essencial" in lowered:
            result["leisure_required"] = "yes"
        elif is_indifferent:
            result["leisure_required"] = "indifferent"

    leisure_keywords = {
        "piscina": "piscina",
        "academia": "academia",
        "gourmet": "gourmet",
        "playground": "playground",
        "quadra": "quadra",
        "cowork": "coworking",
        "salão": "salao",
        "salon": "salao",
        "churras": "churrasqueira",
        "brinquedoteca": "brinquedoteca",
        "sauna": "sauna",
    }
    leisure_found = []
    for key, canonical in leisure_keywords.items():
        if key in lowered:
            leisure_found.append(canonical)
    if leisure_found:
        result["leisure_features"] = leisure_found

    # Floor preference
    floor_pref = extract_floor_preference(text)
    if floor_pref:
        result["floor_pref"] = floor_pref

    # Sun preference
    sun_pref = extract_sun_preference(text)
    if sun_pref:
        result["sun_pref"] = sun_pref

    return result


def enrich_with_regex(message: str, state, updates: Dict[str, Any], known_neighborhoods: Iterable[str] | None = None) -> Dict[str, Any]:
    """
    Usa extractor determinístico para capturar campos que o LLM não trouxe.
    Apenas preenche campos ausentes.

    Args:
        message: Mensagem do usuário
        state: Estado da sessão (SessionState)
        updates: Updates já extraídos pelo LLM

    Returns:
        Dicionário de updates enriquecido com detecções por regex
    """
    fallback = extract_criteria(message, known_neighborhoods or [])
    merged = dict(updates)
    for k, v in fallback.items():
        if v is None:
            continue
        current = merged.get(k)
        already_set = state.triage_fields.get(k)
        if current and current.get("value") == v and current.get("status") != "confirmed":
            merged[k]["status"] = "confirmed"
            merged[k]["raw_text"] = merged[k].get("raw_text") or message
            continue
        if (not current or current.get("value") is None) and not (already_set and already_set.get("status") == "confirmed"):
            merged[k] = {"value": v, "status": "confirmed", "raw_text": message}
    return merged
