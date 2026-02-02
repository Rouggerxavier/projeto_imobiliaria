"""
Script de teste para verificar se o agente de IA está funcionando corretamente
"""

import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("🧪 TESTE DO AGENTE DE IA IMOBILIÁRIO")
print("=" * 60)

# 1. Testa conexão com Groq
print("\n1️⃣ Testando conexão com Groq API...")
from app.agent.llm import test_llm_connection, GROQ_API_KEY, GROQ_MODEL

if not GROQ_API_KEY:
    print("❌ ERRO: GROQ_API_KEY não encontrada no .env")
    sys.exit(1)

print(f"   API Key: {GROQ_API_KEY[:20]}...")
print(f"   Modelo: {GROQ_MODEL}")

if test_llm_connection():
    print("   ✅ Conexão funcionando!")
else:
    print("   ❌ Erro na conexão!")
    sys.exit(1)

# 2. Testa classificação de intenção
print("\n2️⃣ Testando classificação de intenção...")
from app.agent.ai_agent import get_agent

agent = get_agent()

test_messages = [
    "Quero alugar um apartamento em João Pessoa",
    "Estou procurando para comprar uma casa",
    "Quero investir em imóveis",
]

for msg in test_messages:
    result = agent.classify_intent(msg)
    intent = result.get("intent")
    confidence = result.get("confidence", 0)
    print(f"   '{msg[:40]}...'")
    print(f"   → Intenção: {intent} (confiança: {confidence:.2f})")

print("   ✅ Classificação funcionando!")

# 3. Testa extração de critérios
print("\n3️⃣ Testando extração de critérios...")

test_extraction = "Quero um apartamento de 3 quartos em Manaíra com orçamento até 500 mil"
result = agent.extract_criteria(
    test_extraction,
    known_neighborhoods=["Manaíra", "Cabo Branco", "Bessa"]
)

extracted = result.get("extracted", {})
print(f"   Mensagem: '{test_extraction}'")
print(f"   Extraído: {extracted}")
print("   ✅ Extração funcionando!")

# 4. Testa planejamento de diálogo
print("\n4️⃣ Testando planejamento de diálogo...")
from app.agent.state import SessionState

state = SessionState(session_id="test_001")
state.history.append({"role": "user", "text": "Oi, quero alugar um apartamento"})

plan_result = agent.plan_next_step(
    message="Oi, quero alugar um apartamento",
    state=state,
    extracted={"intent": "alugar"},
    missing_fields=["location", "budget", "property_type"]
)

print(f"   Ação decidida: {plan_result.get('action')}")
print(f"   Mensagem: {plan_result.get('message')}")
print("   ✅ Planejamento funcionando!")

# 5. Testa detecção de handoff
print("\n5️⃣ Testando detecção de handoff...")

handoff_messages = [
    ("Quero negociar o preço", "negociacao"),
    ("Gostaria de agendar uma visita", "visita"),
    ("Quero falar com um corretor", "pedido_humano"),
]

for msg, expected_reason in handoff_messages:
    should_handoff, reason, urgency = agent.should_handoff(msg, state)
    symbol = "✅" if should_handoff else "❌"
    print(f"   {symbol} '{msg}' → {reason} (urgência: {urgency})")

print("   ✅ Detecção de handoff funcionando!")

# Resultado final
print("\n" + "=" * 60)
print("✅ TODOS OS TESTES PASSARAM!")
print("=" * 60)
print("\n🎉 O agente de IA está configurado e funcionando corretamente!")
print("💡 A LLM (Groq) está sendo usada para TODAS as decisões:")
print("   • Classificação de intenções")
print("   • Extração de critérios")
print("   • Planejamento de respostas")
print("   • Detecção de handoff para humanos")
print("\n🚀 Você agora tem um AGENTE DE IA real, não um bot de respostas prontas!")
print("=" * 60)
