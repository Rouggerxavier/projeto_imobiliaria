"""Teste do fluxo humanizado Grankasa - end to end"""
import requests
import json

BASE = "http://localhost:8000/webhook"
SID = "test-grankasa-humanized-001"

msgs = [
    "bom dia",
    "quero comprar um apartamento em manaira, joao pessoa, perto da orla, com pelo menos 3 quartos, 2 suites e 2 vagas",
    "minha faixa de preco e de 700 mil a 1 milhao",
    "prefiro seguir pesquisando",
    "Rougger Xavier",
    "83991234567",
]

print("=" * 60)
print("TESTE FLUXO HUMANIZADO GRANKASA")
print("=" * 60)

for m in msgs:
    r = requests.post(BASE, json={"session_id": SID, "message": m})
    d = r.json()
    bot_reply = d.get("reply", "[sem resposta]")
    print(f"\nCLIENTE: {m}")
    print(f"BOT:\n{bot_reply}")
    print("-" * 60)
