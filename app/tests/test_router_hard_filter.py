from agent.router import Agent, AgentStats, choose_agent, save_stats
from agent.state import SessionState


def _agent(id_, neighborhoods, specialties=None, active=True):
    return Agent(
        id=id_,
        name=id_,
        whatsapp="+550000",
        active=active,
        ops=["buy", "rent"],
        coverage_neighborhoods=neighborhoods,
        micro_location_tags=[],
        price_min=0,
        price_max=10_000_000,
        specialties=specialties or [],
        daily_capacity=10,
        priority_tier="standard",
    )


def _empty_stats(path):
    save_stats({}, path=str(path))
    return str(path)


def test_router_excludes_neighborhood_mismatch(tmp_path):
    lead = SessionState("lead1")
    lead.intent = "comprar"
    lead.set_criterion("neighborhood", "Manaira")
    agents = [
        _agent("mismatch", ["Bessa"]),
    ]
    stats_path = _empty_stats(tmp_path / "agent_stats.json")
    result = choose_agent(agents, lead, stats_path=stats_path, correlation_id="test_router_mismatch")
    assert result is None


def test_router_allows_match_only(tmp_path):
    lead = SessionState("lead2")
    lead.intent = "comprar"
    lead.set_criterion("neighborhood", "Manaira")
    agents = [
        _agent("mismatch", ["Bessa"]),
        _agent("match", ["Manaira"]),
    ]
    stats_path = _empty_stats(tmp_path / "agent_stats.json")
    res = choose_agent(agents, lead, stats_path=stats_path, correlation_id="test_router_match")
    assert res is not None
    assert res.agent_id == "match"
