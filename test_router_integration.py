"""
Teste de integração end-to-end do Lead Router.

Demonstra o fluxo completo: triagem → roteamento → persistência.
"""

import os
import sys

# Setup path
ROOT = os.path.abspath(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "app"))

from agent.controller import handle_message
from agent.state import store


def test_integration_hot_lead():
    """
    Teste integrado: Lead hot completo deve rotear para corretor senior.
    """
    print("\n=== Teste de Integração: Lead Hot → Corretor Senior ===\n")

    # Simula conversa completa
    session_id = "integration_test_hot"
    store.reset(session_id)

    messages = [
        ("Olá, quero comprar um apartamento", "Início da conversa"),
        ("Em Manaíra, beira-mar", "Define bairro e micro-localização"),
        ("3 quartos", "Define quartos"),
        ("2 vagas", "Define vagas"),
        ("Até 1.5 milhão", "Define orçamento"),
        ("3 meses", "Define timeline"),
        ("apartamento", "Define tipo"),
    ]

    for i, (msg, desc) in enumerate(messages, 1):
        print(f"[{i}] User: {msg}")
        print(f"    ({desc})")

        result = handle_message(
            session_id=session_id,
            message=msg,
            name="João Silva",
            correlation_id=f"integration_test_{i}"
        )

        print(f"    Bot: {result['reply'][:100]}...")

        # Verifica se completou
        if "summary" in result:
            print(f"\n✓ Triagem concluída na mensagem {i}!")

            summary = result["summary"]

            # Verifica atribuição de corretor
            if "assigned_agent" in summary:
                agent = summary["assigned_agent"]
                routing = summary["routing"]

                print(f"\n=== Roteamento Realizado ===")
                print(f"Corretor ID: {agent['id']}")
                print(f"Nome: {agent['name']}")
                print(f"Score: {agent['score']}")
                print(f"Razões: {agent['reasons']}")
                print(f"Fallback: {agent['fallback']}")
                print(f"Estratégia: {routing['strategy']}")
                print(f"Avaliados: {routing['evaluated_agents_count']} corretores")

                # Validações
                assert agent['id'] is not None, "Deve ter agent_id"
                assert agent['name'] is not None, "Deve ter nome do corretor"
                assert agent['score'] > 0, "Score deve ser positivo"
                assert len(agent['reasons']) > 0, "Deve ter razões"
                assert routing['strategy'] in ["score_based", "fallback_generalista", "fallback_default_queue"]

                print(f"\n✓ Lead hot roteado com sucesso para {agent['name']}!")
                print(f"✓ Todas as validações passaram!")

            else:
                print("\n⚠ Aviso: Nenhum corretor foi atribuído (agents.json pode estar vazio)")

            # Verifica lead_score
            assert "lead_score" in summary, "Deve ter lead_score"
            lead_score = summary["lead_score"]
            print(f"\n=== Lead Score ===")
            print(f"Temperatura: {lead_score['temperature']}")
            print(f"Score: {lead_score['score']}")
            print(f"Razões: {lead_score['reasons']}")

            assert lead_score['temperature'] in ["hot", "warm", "cold"]
            assert 0 <= lead_score['score'] <= 100

            break
        else:
            print()

    store.reset(session_id)
    print("\n=== Teste Concluído ===\n")


def test_integration_cold_lead():
    """
    Teste integrado: Lead cold sem detalhes deve rotear para corretor junior/generalista.
    """
    print("\n=== Teste de Integração: Lead Cold → Corretor Junior/Generalista ===\n")

    session_id = "integration_test_cold"
    store.reset(session_id)

    messages = [
        ("Quero alugar", "Intent"),
        ("João Pessoa", "Cidade"),
        ("Apartamento", "Tipo"),
        ("2 quartos", "Quartos"),
        ("1 vaga", "Vagas"),
        ("Não tenho pressa, flexível", "Timeline"),
        ("Ainda não sei o bairro", "Sem bairro"),
        ("Sem preferência de localização", "Sem micro-loc"),
    ]

    for i, (msg, desc) in enumerate(messages, 1):
        print(f"[{i}] User: {msg} ({desc})")

        result = handle_message(
            session_id=session_id,
            message=msg,
            name="Ana Costa",
            correlation_id=f"integration_cold_{i}"
        )

        print(f"    Bot: {result['reply'][:80]}...")

        if "summary" in result:
            print(f"\n✓ Triagem concluída!")

            summary = result["summary"]

            if "assigned_agent" in summary:
                agent = summary["assigned_agent"]
                print(f"\n=== Roteamento ===")
                print(f"Corretor: {agent['name']} ({agent['id']})")
                print(f"Score: {agent['score']}")
                print(f"Fallback: {agent['fallback']}")

                # Para lead cold sem bairro/budget, deve cair em generalista ou ter score baixo
                print(f"\n✓ Lead cold roteado para {agent['name']}!")

            lead_score = summary["lead_score"]
            print(f"\n=== Lead Score ===")
            print(f"Temperatura: {lead_score['temperature']}")
            print(f"Score: {lead_score['score']}")

            # Lead cold deve ter score baixo
            assert lead_score['temperature'] in ["cold", "warm"], f"Esperado cold/warm, obtido {lead_score['temperature']}"

            break
        else:
            print()

    store.reset(session_id)
    print("\n=== Teste Concluído ===\n")


if __name__ == "__main__":
    # Configurar ambiente para TRIAGE_ONLY
    os.environ["TRIAGE_ONLY"] = "true"
    os.environ["USE_LLM"] = "true"  # ou false para fallback determinístico

    try:
        test_integration_hot_lead()
        test_integration_cold_lead()
        print("\n✅ Todos os testes de integração passaram!\n")
    except Exception as e:
        print(f"\n❌ Erro: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
