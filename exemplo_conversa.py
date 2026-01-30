"""
Exemplo de uso do Agente de IA Imobiliário
Simula uma conversa completa com o agente
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.agent.controller import handle_message

def print_separator():
    print("\n" + "=" * 70 + "\n")

def simulate_conversation():
    """Simula uma conversa realista com o agente"""
    
    session_id = "demo_001"
    
    print("🤖 AGENTE DE IA IMOBILIÁRIO - DEMONSTRAÇÃO")
    print_separator()
    
    # Conversa 1: Aluguel
    messages = [
        ("Cliente inicia", "Oi, bom dia!", "João Silva"),
        ("Cliente expressa interesse", "Quero alugar um apartamento", None),
        ("Cliente fornece localização", "Quero em Manaíra", None),
        ("Cliente define orçamento", "Meu orçamento é até 3 mil por mês", None),
        ("Cliente especifica tipo", "Apartamento de 2 quartos", None),
    ]
    
    for step, message_tuple in enumerate(messages, 1):
        label, message, name = message_tuple
        print(f"[{step}] 👤 CLIENTE ({label}): {message}")
        
        result = handle_message(
            session_id=session_id,
            message=message,
            name=name if name else None
        )
        
        reply = result.get("reply", "")
        properties = result.get("properties", [])
        
        print(f"    🤖 AGENTE: {reply}")
        
        if properties:
            print(f"    📊 Encontrou {len(properties)} imóveis")
        
        print()
    
    print_separator()
    print("✅ Conversa concluída!")
    print("\n📊 ESTATÍSTICAS:")
    print(f"   • Total de mensagens: {len(messages)}")
    print(f"   • Sessão: {session_id}")
    print(f"   • Cliente: {messages[0][2]}")
    print("\n💡 Todas as decisões foram tomadas pela IA (Groq LLM)")
    print("   Não foi usado nenhum template fixo ou keyword hardcoded!")
    print_separator()

if __name__ == "__main__":
    simulate_conversation()
