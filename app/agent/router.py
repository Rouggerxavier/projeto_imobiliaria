"""
Lead Router - Roteamento Determinístico de Leads para Corretores

Sistema baseado em regras e pontuação para atribuir leads aos corretores mais adequados,
sem uso de LLM. Inclui controle de capacidade diária e round-robin para balanceamento.
"""

from __future__ import annotations
import json
import os
import threading
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from .state import SessionState
from .persistence import _ensure_dir  # reuse helper for directory creation


# Lock global para escrita atômica em agent_stats.json
_stats_lock = threading.Lock()
_routing_log_lock = threading.Lock()

# Configuração
EXPOSE_AGENT_CONTACT = os.getenv("EXPOSE_AGENT_CONTACT", "false").lower() in ("true", "1", "yes")

# Caminho padrão para log JSONL do roteamento (monitoramento/dashboard)
DEFAULT_ROUTING_LOG_PATH = os.getenv("ROUTING_LOG_PATH")
if not DEFAULT_ROUTING_LOG_PATH:
    base_dir = "/mnt/data" if os.path.exists("/mnt/data") else "data"
    DEFAULT_ROUTING_LOG_PATH = os.path.join(base_dir, "routing_log.jsonl")


@dataclass
class Agent:
    """Representa um corretor/agente de vendas."""
    id: str
    name: str
    whatsapp: str
    active: bool
    ops: List[str]  # ["buy", "rent"]
    coverage_neighborhoods: List[str]
    micro_location_tags: List[str]
    price_min: int
    price_max: int
    specialties: List[str]
    daily_capacity: int
    priority_tier: str  # "senior", "standard", "junior"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Agent:
        """Cria Agent a partir de dicionário."""
        return cls(
            id=data["id"],
            name=data["name"],
            whatsapp=data["whatsapp"],
            active=data.get("active", True),
            ops=data.get("ops", []),
            coverage_neighborhoods=data.get("coverage_neighborhoods", []),
            micro_location_tags=data.get("micro_location_tags", []),
            price_min=data.get("price_min", 0),
            price_max=data.get("price_max", 999999999),
            specialties=data.get("specialties", []),
            daily_capacity=data.get("daily_capacity", 20),
            priority_tier=data.get("priority_tier", "standard"),
        )


@dataclass
class AgentStats:
    """Estatísticas de atribuição de um agente."""
    assigned_today: int = 0
    last_assigned_at: Optional[str] = None


@dataclass
class RoutingResult:
    """Resultado do roteamento de um lead."""
    agent_id: str
    agent_name: str
    whatsapp: str
    score: int
    reasons: List[str]
    strategy: str
    evaluated_agents_count: int
    fallback: bool = False


def load_agents(path: str = "data/agents.json") -> List[Agent]:
    """
    Carrega lista de agentes do arquivo JSON.

    Args:
        path: Caminho para o arquivo JSON

    Returns:
        Lista de objetos Agent
    """
    # Tenta carregar do path especificado, senão tenta example
    if not os.path.exists(path):
        example_path = path.replace(".json", ".example.json")
        if os.path.exists(example_path):
            path = example_path
        else:
            print(f"[ROUTER] Arquivo de agentes não encontrado: {path}")
            return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        agents = [Agent.from_dict(a) for a in data]
        print(f"[ROUTER] Carregados {len(agents)} agentes de {path}")
        return agents
    except Exception as e:
        print(f"[ROUTER] Erro ao carregar agentes: {e}")
        return []


def load_stats(path: str = "data/agent_stats.json") -> Dict[str, AgentStats]:
    """
    Carrega estatísticas dos agentes com reset diário automático.

    Args:
        path: Caminho para o arquivo de stats

    Returns:
        Dicionário {agent_id: AgentStats}
    """
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Verifica se precisa resetar (mudança de dia)
        last_reset = data.get("last_reset_date")
        today = str(date.today())

        stats = {}
        agents_data = data.get("agents", {})

        if last_reset != today:
            # Reset diário: zera assigned_today
            print(f"[ROUTER] Reset diário de stats (last={last_reset}, today={today})")
            for agent_id, agent_data in agents_data.items():
                stats[agent_id] = AgentStats(
                    assigned_today=0,
                    last_assigned_at=agent_data.get("last_assigned_at")
                )
        else:
            # Carrega stats normalmente
            for agent_id, agent_data in agents_data.items():
                stats[agent_id] = AgentStats(
                    assigned_today=agent_data.get("assigned_today", 0),
                    last_assigned_at=agent_data.get("last_assigned_at")
                )

        return stats
    except Exception as e:
        print(f"[ROUTER] Erro ao carregar stats: {e}")
        return {}


def save_stats(stats: Dict[str, AgentStats], path: str = "data/agent_stats.json") -> None:
    """
    Salva estatísticas dos agentes com escrita atômica.

    Args:
        stats: Dicionário de estatísticas
        path: Caminho para o arquivo
    """
    with _stats_lock:
        try:
            # Prepara dados
            data = {
                "last_reset_date": str(date.today()),
                "agents": {}
            }

            for agent_id, agent_stats in stats.items():
                data["agents"][agent_id] = {
                    "assigned_today": agent_stats.assigned_today,
                    "last_assigned_at": agent_stats.last_assigned_at
                }

            # Escrita atômica: temp + rename
            temp_path = path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Rename atômico
            if os.path.exists(path):
                os.replace(temp_path, path)
            else:
                os.rename(temp_path, path)

        except Exception as e:
            print(f"[ROUTER] Erro ao salvar stats: {e}")


def _log_routing_event(event: Dict[str, Any], path: Optional[str]) -> None:
    """Registra evento JSONL de roteamento (para dashboard/monitoramento)."""
    if not path:
        return
    try:
        _ensure_dir(path)
        line = json.dumps(event, ensure_ascii=False)
        with _routing_log_lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as e:
        print(f"[ROUTER] warn=log_failed error={e}")


def _normalize_neighborhood(neighborhood: Optional[str]) -> Optional[str]:
    """Normaliza nome de bairro para comparação."""
    if not neighborhood:
        return None
    return neighborhood.lower().strip()


def _normalize_micro_location(micro: Optional[str]) -> Optional[str]:
    """Normaliza micro-localização para comparação."""
    if not micro:
        return None
    # Remove parênteses e normaliza
    normalized = micro.lower().strip()
    normalized = normalized.replace("(praia)", "").replace("_da_praia", "").strip()
    return normalized


def _get_intent_type(intent: Optional[str]) -> Optional[str]:
    """Converte intent para tipo de operação."""
    if not intent:
        return None
    intent_lower = intent.lower()
    if intent_lower in ("alugar", "aluguel"):
        return "rent"
    if intent_lower in ("comprar", "compra"):
        return "buy"
    if intent_lower == "investir":
        return "buy"  # investimento = compra
    return None


def score_agent(agent: Agent, lead_state: SessionState, stats: Dict[str, AgentStats], priority: bool = False) -> Tuple[int, List[str]]:
    """
    Calcula pontuação de um agente para um lead específico.

    Args:
        agent: Agente a ser avaliado
        lead_state: Estado do lead
        stats: Estatísticas dos agentes
        priority: Se True, ignora limite de capacidade (para HOT leads)

    Returns:
        (score, reasons) onde score é int e reasons é lista de strings explicativas
    """
    score = 0
    reasons = []

    # Verifica ativo
    if not agent.active:
        return -1000, ["agent_inactive"]

    # Compatibilidade de operação
    intent_type = _get_intent_type(lead_state.intent)
    if intent_type and intent_type not in agent.ops:
        return -1000, [f"operation_incompatible_{intent_type}"]

    # Bairro - hard filter
    lead_neighborhood = _normalize_neighborhood(lead_state.criteria.neighborhood)
    is_generalist = ("generalista" in agent.specialties) or ("*" in agent.coverage_neighborhoods)
    if lead_neighborhood:
        agent_neighborhoods = [_normalize_neighborhood(n) for n in agent.coverage_neighborhoods]
        if agent_neighborhoods and lead_neighborhood not in agent_neighborhoods and not is_generalist:
            return -1000, ["neighborhood_mismatch_hard"]

    if lead_neighborhood:
        if lead_neighborhood in agent_neighborhoods:
            score += 30
            reasons.append(f"neighborhood_match_{lead_neighborhood}")
        elif agent.coverage_neighborhoods:  # Tem cobertura mas não bate
            score -= 10
            reasons.append(f"neighborhood_mismatch")
    else:
        # Lead sem bairro: generalista ganha bônus
        if not agent.coverage_neighborhoods or "generalista" in agent.specialties:
            score += 5
            reasons.append("generalista_no_neighborhood")

    # Micro-localização
    lead_micro = _normalize_micro_location(lead_state.criteria.micro_location)
    if lead_micro:
        agent_micros = [_normalize_micro_location(m) for m in agent.micro_location_tags]
        if lead_micro in agent_micros:
            score += 15
            reasons.append(f"micro_location_match_{lead_micro}")

    # Faixa de preço
    lead_budget = lead_state.criteria.budget
    if lead_budget:
        if agent.price_min <= lead_budget <= agent.price_max:
            score += 20
            reasons.append(f"price_range_match")
        elif lead_budget < agent.price_min:
            score -= 15
            reasons.append("price_too_low")
        elif lead_budget > agent.price_max:
            score -= 15
            reasons.append("price_too_high")

    # Lead score (temperatura) + tier do agente
    temp = lead_state.lead_score.temperature
    tier = agent.priority_tier

    if temp == "hot" and tier == "senior":
        score += 10
        reasons.append("hot_senior_match")
    elif temp == "warm" and tier == "standard":
        score += 5
        reasons.append("warm_standard_match")
    elif temp == "cold" and tier == "junior":
        score += 5
        reasons.append("cold_junior_match")

    # Specialties
    bedrooms = lead_state.criteria.bedrooms or 0

    if "alto_padrao" in agent.specialties and lead_budget and lead_budget >= 900000:
        score += 10
        reasons.append("specialty_alto_padrao")

    if "familia" in agent.specialties and bedrooms >= 3:
        score += 10
        reasons.append("specialty_familia")

    if "pet_friendly" in agent.specialties and lead_state.criteria.pet:
        score += 5
        reasons.append("specialty_pet")

    # Capacidade diária - penalidade forte para evitar sobrecarga
    # Exceção: HOT leads (priority=True) ignoram limite de capacidade
    agent_stats = stats.get(agent.id, AgentStats())
    if not priority and agent_stats.assigned_today >= agent.daily_capacity:
        return -1000, [f"capacity_reached_{agent_stats.assigned_today}/{agent.daily_capacity}"]
    elif priority and agent_stats.assigned_today >= agent.daily_capacity:
        # HOT lead: aceita mas com pequena penalização (não bloqueia)
        score -= 5
        reasons.append(f"priority_override_capacity_{agent_stats.assigned_today}/{agent.daily_capacity}")

    return score, reasons


def choose_agent(
    agents: List[Agent],
    lead_state: SessionState,
    stats_path: str = "data/agent_stats.json",
    correlation_id: Optional[str] = None,
    priority: bool = False,
    routing_log_path: Optional[str] = DEFAULT_ROUTING_LOG_PATH,
) -> Optional[RoutingResult]:
    """
    Escolhe o melhor agente para um lead baseado em pontuação e regras.

    Args:
        agents: Lista de agentes disponíveis
        lead_state: Estado do lead
        stats_path: Caminho para arquivo de stats
        correlation_id: ID de correlação para logs
        priority: Se True, ignora limite de capacidade (para HOT leads)

    Returns:
        RoutingResult com agente escolhido ou None se nenhum disponível
    """
    if not agents:
        print(f"[ROUTER] no_agents_available correlation={correlation_id}")
        return None

    # Carrega stats
    stats = load_stats(stats_path)
    allowed_ids = {a.id for a in agents}
    stats = {k: v for k, v in stats.items() if k in allowed_ids}

    # Calcula scores
    scored_agents: List[Tuple[Agent, int, List[str]]] = []
    match_found = False
    for agent in agents:
        lead_neighborhood = _normalize_neighborhood(lead_state.criteria.neighborhood)
        if lead_neighborhood and _normalize_neighborhood(lead_neighborhood) in [
            _normalize_neighborhood(n) for n in agent.coverage_neighborhoods
        ]:
            match_found = True
        score, reasons = score_agent(agent, lead_state, stats, priority=priority)
        if score > -1000:  # Filtra incompatíveis
            scored_agents.append((agent, score, reasons))

    if not scored_agents:
        print(f"[ROUTER] no_compatible_agents correlation={correlation_id}")
        return _fallback_agent(agents, stats, lead_state, allow_mismatch=match_found, stats_path=stats_path, correlation_id=correlation_id, routing_log_path=routing_log_path)

    # Ordena por score (desc), depois por assigned_today (asc), depois por last_assigned_at (asc/null first)
    def sort_key(item: Tuple[Agent, int, List[str]]) -> Tuple[int, int, str]:
        agent, score, _ = item
        agent_stats = stats.get(agent.id, AgentStats())
        assigned = agent_stats.assigned_today
        last_assigned = agent_stats.last_assigned_at or "1970-01-01T00:00:00Z"
        return (-score, assigned, last_assigned)  # -score para desc

    scored_agents.sort(key=sort_key)

    # Escolhe o melhor
    best_agent, best_score, best_reasons = scored_agents[0]

    # Atualiza stats
    now = datetime.utcnow().isoformat() + "Z"
    if best_agent.id not in stats:
        stats[best_agent.id] = AgentStats()

    stats[best_agent.id].assigned_today += 1
    stats[best_agent.id].last_assigned_at = now

    # Salva stats
    save_stats(stats, stats_path)

    # Logs estruturados (console + JSONL)
    print(
        "[ROUTER] assigned_agent={agent_id} name={agent_name} temp={temp} score={score} reasons={reasons} correlation={cid}".format(
            agent_id=best_agent.id,
            agent_name=best_agent.name,
            temp=lead_state.lead_score.temperature,
            score=best_score,
            reasons=best_reasons,
            cid=correlation_id,
        )
    )
    _log_routing_event(
        {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "correlation_id": correlation_id,
            "agent_id": best_agent.id,
            "agent_name": best_agent.name,
            "score": best_score,
            "reasons": best_reasons,
            "fallback": False,
            "strategy": "score_based",
            "evaluated_agents": len(scored_agents),
            "lead_temperature": lead_state.lead_score.temperature,
            "lead_session_id": lead_state.session_id,
        },
        routing_log_path,
    )

    return RoutingResult(
        agent_id=best_agent.id,
        agent_name=best_agent.name,
        whatsapp=best_agent.whatsapp,
        score=best_score,
        reasons=best_reasons,
        strategy="score_based",
        evaluated_agents_count=len(scored_agents),
        fallback=False
    )


def _fallback_agent(
    agents: List[Agent],
    stats: Dict[str, AgentStats],
    lead_state: Optional[SessionState] = None,
    allow_mismatch: bool = False,
    stats_path: str = "data/agent_stats.json",
    correlation_id: Optional[str] = None,
    routing_log_path: Optional[str] = DEFAULT_ROUTING_LOG_PATH,
) -> Optional[RoutingResult]:
    """
    Seleciona agente fallback quando nenhum é compatível.
    Escolhe generalista ou agente com menor carga.
    """
    lead_neighborhood = _normalize_neighborhood(lead_state.criteria.neighborhood) if lead_state else None
    desired_op = _get_intent_type(lead_state.intent) if lead_state else None

    # Busca generalistas ativos (restritos por regra de bairro)
    generalistas = []
    for a in agents:
        if not a.active:
            continue
        has_wildcard = "*" in a.coverage_neighborhoods
        is_generalist = "generalista" in a.specialties
        if desired_op and desired_op not in a.ops:
            continue
        if lead_neighborhood:
            if has_wildcard or is_generalist:
                generalistas.append(a)
        else:
            if is_generalist or has_wildcard or not a.coverage_neighborhoods:
                generalistas.append(a)

    if generalistas:
        # Escolhe generalista com menor assigned_today
        generalistas.sort(key=lambda a: stats.get(a.id, AgentStats()).assigned_today)
        fallback = generalistas[0]

        # Atualiza stats
        if fallback.id not in stats:
            stats[fallback.id] = AgentStats()
        stats[fallback.id].assigned_today += 1
        stats[fallback.id].last_assigned_at = datetime.utcnow().isoformat() + "Z"
        save_stats(stats, stats_path)

        print(f"[ROUTER] fallback=generalista agent={fallback.id} correlation={correlation_id}")
        _log_routing_event(
            {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "correlation_id": correlation_id,
                "agent_id": fallback.id,
                "agent_name": fallback.name,
                "score": 0,
                "reasons": ["fallback_generalista"],
                "fallback": True,
                "strategy": "fallback_generalista",
                "evaluated_agents": len(agents),
                "lead_temperature": None,
                "lead_session_id": None,
            },
            routing_log_path,
        )

        return RoutingResult(
            agent_id=fallback.id,
            agent_name=fallback.name,
            whatsapp=fallback.whatsapp,
            score=0,
            reasons=["fallback_generalista"],
            strategy="fallback_generalista",
            evaluated_agents_count=len(agents),
            fallback=True
        )

    # Última opção: qualquer agente ativo compatível com operação com menor carga
    active = [a for a in agents if a.active and (not desired_op or desired_op in a.ops)]
    if active:
        active.sort(key=lambda a: stats.get(a.id, AgentStats()).assigned_today)
        fallback = active[0]

        if lead_neighborhood and not allow_mismatch:
            print(f"[ROUTER] no_match neighborhood={lead_neighborhood} correlation={correlation_id}")
            return None

        strategy = "fallback_default_queue_mismatch" if lead_neighborhood else "fallback_default_queue"
        print(f"[ROUTER] {strategy} agent={fallback.id} correlation={correlation_id}")

        if fallback.id not in stats:
            stats[fallback.id] = AgentStats()
        stats[fallback.id].assigned_today += 1
        stats[fallback.id].last_assigned_at = datetime.utcnow().isoformat() + "Z"
        save_stats(stats, stats_path)
        _log_routing_event(
            {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "correlation_id": correlation_id,
                "agent_id": fallback.id,
                "agent_name": fallback.name,
                "score": 0,
                "reasons": ["fallback_default_queue"],
                "fallback": True,
                "strategy": strategy,
                "evaluated_agents": len(agents),
                "lead_temperature": None,
                "lead_session_id": None,
            },
            routing_log_path,
        )

        return RoutingResult(
            agent_id=fallback.id,
            agent_name=fallback.name,
            whatsapp=fallback.whatsapp,
            score=0,
            reasons=["fallback_default_queue"],
            strategy=strategy,
            evaluated_agents_count=len(agents),
            fallback=True
        )

    print(f"[ROUTER] no_fallback_available correlation={correlation_id}")
    return None


def route_lead(
    lead_state: SessionState,
    agents_path: str = "data/agents.json",
    stats_path: str = "data/agent_stats.json",
    correlation_id: Optional[str] = None,
    priority: bool = False,
    routing_log_path: Optional[str] = DEFAULT_ROUTING_LOG_PATH,
) -> Optional[RoutingResult]:
    """
    Função principal de roteamento. Carrega agentes e escolhe o melhor.

    Args:
        lead_state: Estado do lead
        agents_path: Caminho para arquivo de agentes
        stats_path: Caminho para arquivo de stats
        correlation_id: ID de correlação
        priority: Se True, ignora limite de capacidade (para HOT leads)

    Returns:
        RoutingResult ou None se falhar
    """
    try:
        agents = load_agents(agents_path)
        if not agents:
            print(f"[ROUTER] no_agents_loaded fallback=null correlation={correlation_id}")
            return None

        return choose_agent(agents, lead_state, stats_path, correlation_id, priority=priority, routing_log_path=routing_log_path)

    except Exception as e:
        print(f"[ROUTER] error={e} fallback=null correlation={correlation_id}")
        return None
