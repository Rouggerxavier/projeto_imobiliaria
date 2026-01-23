<<<<<<< HEAD
﻿# Agente de Pré-atendimento Imobiliário (WhatsApp-ready)

Backend FastAPI com orquestrador determinístico para leads de compra/aluguel de imóveis via WhatsApp (simulado por HTTP). Inclui base dummy de 46 imóveis, regras de qualificação, gates anti-alucinação e testes automatizados.

## Requisitos
- Python 3.11+
- pip

## Instalação
`ash
python -m venv .venv
./.venv/Scripts/activate   # PowerShell
pip install -r requirements.txt
cp .env.example .env
`

## Rodar local
`ash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
`
Healthcheck: GET /health

## Webhook (MVP)
Endpoint: POST /webhook
Body JSON:
`json
{
  "session_id": "lead-123",
  "message": "quero alugar um ape em Manaíra até 3 mil, 2 quartos",
  "name": "Maria"
}
`
Resposta típica:
`json
{
  "reply": "Encontrei estas opções... Quer agendar visita ou refinar (bairro/quartos/orçamento)?",
  "properties": ["JP-MAN-006", "JP-MAN-002"],
  "state": {
    "session_id": "lead-123",
    "intent": "alugar",
    "criteria": {"city": "Joao Pessoa", "neighborhood": "Manaira", "property_type": "apartamento", "bedrooms": 2},
    "human_handoff": false,
    "last_suggestions": ["JP-MAN-006", "JP-MAN-002"]
  }
}
`
Use session_id para manter contexto entre mensagens.

## Fluxos cobertos
- **Happy path**: alugar em Manaira até 3k → lista 3–6 opções → CTA agendar/refinar.
- **Falta localização**: pergunta apenas cidade/bairro.
- **Falta orçamento**: pergunta teto mensal/total conforme intenção.
- **Zero resultados**: sugere ampliar orçamento ou bairros vizinhos.
- **Agendamento**: detecta palavra-chave “visita” e solicita horários/modo.
- **Handoff humano**: dispara quando há pedido de negociação, humano explícito ou urgência alta com orçamento claro.

## Arquitetura
- pp/main.py – FastAPI + endpoint /webhook.
- pp/agent/controller.py – orquestra fluxo, decide próxima ação, aplica gates.
- pp/agent/extractor.py – extrai critérios (localização, tipo, quartos, orçamento, pet, mobiliado, urgência).
- pp/agent/rules.py – gates can_search_properties / can_answer_about_property e política de pergunta única.
- pp/agent/tools.py – base dummy (pp/data/properties.json), busca ranqueada, stub de agendamento e handoff.
- pp/agent/prompts.py – prompt de sistema para futura integração com LLM/tool-calling.
- pp/tests – testes unitários para gates, intenção e fluxo feliz.

## Dados dummy
pp/data/properties.json com 46 imóveis (Joao Pessoa, Campina Grande, Recife, Natal, Cabedelo). Campos: id, titulo, cidade, bairro, tipo, quartos, vagas, area_m2, preco_venda, preco_aluguel, condominio, iptu, aceita_pet, mobiliado, descricao_curta, url_fotos.

## Testes
`ash
cd app
pytest
`

## Como evoluir para WhatsApp Cloud API
1) Criar webhook público (ngrok ou deploy) e configurar no app do Meta.
2) No handler /webhook, adaptar para payload do Cloud API (messages[0].text.body, rom, etc.).
3) Responder via POST /messages do WhatsApp com o eply retornado pelo controller.
4) Persistir estado em Redis/DB em vez de memória (SessionState).

## Observações de LGPD e anti-alucinação
- Não solicita dados sensíveis; coleta apenas nome, localização, orçamento e preferências.
- Só responde detalhes de imóveis vindos da base/tool; gates impedem respostas sem dados reais.
- Perguntas sempre uma por vez, priorizando localização > orçamento > tipo.
=======
# projeto_imobiliaria
>>>>>>> e3bbbe7a8f0abdf756c1479dcf94b706f0a5fe98
