# Agente de IA Imobiliário (FastAPI + LLM, pronto para WhatsApp)
Backend de pré-atendimento imobiliário com FastAPI, orquestração determinística + LLM (chamada única), base dummy de 46 imóveis e testes automatizados.

## Visão geral
- Uma chamada LLM por mensagem via `llm_decide()` (intent, critérios, handoff e plano juntos).
- Prioridade de provedores: **Google Gemini 2.0 Flash (OpenAI compat)** → OpenAI/OpenRouter → Groq/Ollama → fallback determinístico.
- Guard-rails: enum de ações, validação de filtros/tipos, cache de respostas, backoff em 429, timeout + retry, diferenciação de critérios confirmados vs inferidos.
- Fallback seguro: se LLM falha ou não há API key, usa regras/regex sem travar conversa.

## Arquitetura (atual)
- `app/main.py` – FastAPI, `POST /webhook`, `GET /health`.
- `app/agent/controller.py` – pipeline de mensagem: obtém estado → chama `RealEstateAIAgent.decide()` → executa ação (pergunta, busca, handoff) → atualiza histórico.
- `app/agent/ai_agent.py` – cérebro de decisão; expõe classify/extract/plan/handoff/generate com fallback determinístico.
- `app/agent/llm.py` – integração OpenAI-compatible; `llm_decide()` unificado; cache, rate-limit parsing, streaming opcional; constrói `extra_body` para bases locais.
- `app/agent/rules.py` – gates `can_search_properties`, `missing_critical_fields`, política de pergunta única.
- `app/agent/extractor.py` e `intent.py` – usados como fallback (regex/keywords).
- `app/agent/tools.py` – busca ranqueada em `app/data/properties.json`, stub de agendamento/handoff humano.
- `app/tests/` – `test_single_llm_call.py`, `test_edge_cases.py`, etc.

### Fluxo de uma mensagem
1) `controller.handle_message()` recebe `{session_id, message, name}`  
2) `ai_agent.decide()` → `llm_decide()` (ou fallback) retorna `{intent, criteria, handoff, plan}`  
3) Gates de segurança ajustam plano; executa ação (`ASK|SEARCH|LIST|REFINE|SCHEDULE|HANDOFF|ANSWER_GENERAL|CLARIFY`)  
4) Resposta devolvida e histórico salvo em memória (`SessionState`).

## Instalação / setup rápido
```
python -m venv .venv
.\.venv\Scripts\activate          # PowerShell
pip install -r requirements.txt
cp .env.example .env             # edite credenciais
```

## Variáveis de ambiente principais
| Chave | Exemplo (default atual) | Observações |
|-------|-------------------------|-------------|
| `OPENAI_API_KEY` | `AIzaSyBVFzrjr-kuNee5eAipcVIWDusMsB2osU0` | Usa endpoint compatível do Gemini. |
| `OPENAI_MODEL` | `gemini-2.0-flash` | Modelo padrão. |
| `OPENAI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` | Necessário para compat OpenAI. |
| `GROQ_API_KEY` | _(vazio)_ | Opcional fallback (ex.: `ollama-local`). |
| `GROQ_MODEL` | _(vazio)_ | Só se usar Groq/Ollama. |
| `USE_LLM` | `true` | `false` ativa somente fallback determinístico. |
| `TRIAGE_ONLY` | `false` | `true` desativa busca/listagem e faz só triagem + resumo. |
| `LLM_TIMEOUT` | `120` | 30s remoto / 120s local sugerido. |
| `LLM_KEEP_ALIVE` | `30m` | Para Ollama local. |
| `LLM_NUM_CTX` | `2048` | Contexto para modelos locais. |
| `LLM_NUM_THREADS` | `8` | Ajuste à CPU local. |

## Execução local
Para evitar bloqueio do `uvicorn.exe` pelo App Control, execute via Python:
```
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Healthcheck: `GET /health`

## Webhook de exemplo
`POST /webhook`
```json
{
  "session_id": "lead-123",
  "message": "quero alugar um ape em Manaíra até 3 mil, 2 quartos",
  "name": "Maria"
}
```
Resposta típica (quando consegue buscar):
```json
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
```
Use `session_id` para manter contexto entre mensagens.

## Base de dados dummy
`app/data/properties.json` com 46 imóveis (João Pessoa, Campina Grande, Recife, Natal, Cabedelo). Campos: id, título, cidade, bairro, tipo, quartos, vagas, área, preços de venda/aluguel, condomínio, IPTU, pet, mobiliado, descrição curta, url de fotos.

## Robustez e anti-alucinação
- Enum estrito de ações (`ASK|SEARCH|LIST|REFINE|SCHEDULE|HANDOFF|ANSWER_GENERAL|CLARIFY`).  
- Validação/sanitização de filtros e tipos no pipeline.  
- Timeout (30s remoto/120s local), retry (2x), cache por mensagem (TTL 5 min).  
- Backoff em 429 com parsing de `retry_after`; desvia para fallback sem spam.  
- Critérios marcados como `confirmed` vs `inferred`; buscas críticas usam confirmados.  
- Sem persona fictícia; tom neutro profissional; não inventa dados fora da base/tool.

## Modo “triagem-only” (MVP)
- Ative com `TRIAGE_ONLY=true`.  
- O agente **não** busca nem lista imóveis; apenas coleta dados com uma pergunta por vez, sem repetir campo já confirmado.  
- Campos críticos: operação, cidade/bairro, tipo, quartos/suíte, vagas, orçamento máx., prazo.  
- Prefs adicionais: andar/posição/vista, lazer, pet, mobiliado, vagas cobertas/soltas, etc.  
- Ao concluir, gera resumo (texto + JSON) e aciona handoff humano com o payload estruturado.  

## Testes
```
python test_ai_agent.py        # garante 1 chamada LLM e fallback em 429
python test_edge_cases.py      # desvio, contradição, inferência x confirmado
pytest                         # roda suíte completa
python exemplo_conversa.py     # simula conversa end-to-end
```

## Próximos passos sugeridos
- Cache persistente (Redis) para sessões e respostas.  
- Métricas de tokens/latência e dashboard simples.  
- Integração WhatsApp Cloud API (adaptar payloads e envio).  
- Streaming opcional para respostas longas.
