# Agente de IA Imobiliário (FastAPI + LLM, pronto para WhatsApp)

Backend de pré-atendimento imobiliário com FastAPI, orquestração determinística + LLM (chamada única), base dummy de 46 imóveis e testes automatizados.

## Visão geral

- Uma chamada LLM por mensagem via `llm_decide()` (intent, critérios, handoff e plano juntos).
- Prioridade de provedores: **Google Gemini 2.0 Flash (OpenAI compat)** → OpenAI/OpenRouter → Groq/Ollama → fallback determinístico.
- Guard-rails: enum de ações, validação de filtros/tipos, cache de respostas, backoff em 429, timeout + retry, diferenciação de critérios confirmados vs inferidos.
- Fallback seguro: se LLM falha ou não há API key, usa regras/regex sem travar conversa.

## Arquitetura (atual) - Refatorada com Separação de Responsabilidades

- `app/main.py` – FastAPI, `POST /webhook`, `GET /health`.
- `app/agent/controller.py` – **Orquestração**: pipeline de mensagem (obtém estado → decide → executa ação → atualiza histórico).
- `app/agent/ai_agent.py` – **Decisões IA**: cérebro de decisão; expõe classify/extract/plan/handoff/generate com fallback determinístico.
- `app/agent/state.py` – **Gerenciamento de Estado**: `SessionState` com `apply_updates()` para detecção automática de conflitos.
- `app/agent/presenter.py` – **Camada de Apresentação**: formatação de preços, imóveis, resumos e mensagens de handoff.
- `app/agent/extractor.py` – **Extração de Dados**: regex determinística + `enrich_with_regex()` para complementar LLM.
- `app/agent/llm.py` – **Integração LLM**: `llm_decide()` unificado; cache, rate-limit parsing, streaming opcional.
- `app/agent/rules.py` – **Regras de Negócio**: gates `can_search_properties`, `missing_critical_fields`, `TRIAGE_ONLY` mode.
- `app/agent/tools.py` – **Ferramentas**: busca ranqueada em `app/data/properties.json`, agendamento/handoff.
- `app/tests/` – **50 testes** (100% pass rate): unit, integration, anti-leak, conflict detection.

### Fluxo de uma mensagem

1. `controller.handle_message()` recebe `{session_id, message, name}`
2. `ai_agent.decide()` → `llm_decide()` (ou fallback) retorna `{intent, criteria, handoff, plan}`
3. Gates de segurança ajustam plano; executa ação (`ASK|SEARCH|LIST|REFINE|SCHEDULE|HANDOFF|ANSWER_GENERAL|CLARIFY`)
4. Resposta devolvida e histórico salvo em memória (`SessionState`).

## Instalação / setup rápido

### 1. Clone e instale dependências

```bash
python -m venv .venv
.\.venv\Scripts\activate          # PowerShell (Windows)
# source .venv/bin/activate       # Linux/Mac
pip install -r requirements.txt
```

### 2. Configure as credenciais (IMPORTANTE!)

```bash
cp .env.example .env              # Copia o template
```

### 3. Escolha seu provedor LLM:

#### 🔵 OPÇÃO A: Google Gemini (gratuito, limite generoso)

1. Acesse: https://aistudio.google.com/apikey
2. Gere uma nova API key
3. Edite `.env` e cole a chave em `OPENAI_API_KEY`
4. Use modelo: `gemini-2.5-flash` (recomendado) ou `gemini-1.5-flash`

#### 🟢 OPÇÃO B: Groq (gratuito, mais estável - RECOMENDADO)

1. Acesse: https://console.groq.com/keys
2. Crie conta e gere API key
3. Edite `.env`:
   - **Comente** as 3 linhas `OPENAI_*` (adicione # no início)
   - **Descomente** as linhas `GROQ_API_KEY` e `GROQ_MODEL`
   - Cole sua chave em `GROQ_API_KEY`

#### 🟣 OPÇÃO C: Ollama (local, sem limites de API)

1. Instale Ollama: https://ollama.ai
2. Execute: `ollama pull llama3.2`
3. Configure no `.env`:
   ```env
   OPENAI_BASE_URL=http://localhost:11434/v1
   OPENAI_MODEL=llama3.2
   OPENAI_API_KEY=ollama
   ```

## Variáveis de ambiente principais

| Chave             | Exemplo (default atual)                                   | Observações                                               |
| ----------------- | --------------------------------------------------------- | --------------------------------------------------------- |
| `OPENAI_API_KEY`  | `sua_chave_aqui`                                          | **NUNCA** exponha chaves em commits!                      |
| `OPENAI_MODEL`    | `gemini-2.5-flash`                                        | Use modelo correto sem prefixo `models/`                  |
| `OPENAI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/`| Barra final `/` é importante                              |
| `GROQ_API_KEY`    | _(vazio)_                                                 | Alternativa ao Gemini (mais estável)                      |
| `GROQ_MODEL`      | `llama-3.3-70b-versatile`                                 | Só se usar Groq                                           |
| `USE_LLM`         | `true`                                                    | `false` ativa somente fallback determinístico             |
| `TRIAGE_ONLY`     | `true`                                                    | `true` desativa busca/listagem e faz só triagem + resumo  |
| `LLM_TIMEOUT`     | `120`                                                     | 30s remoto / 120s local sugerido                          |
| `LLM_KEEP_ALIVE`  | `30m`                                                     | Para Ollama local                                         |
| `LLM_NUM_CTX`     | `2048`                                                    | Contexto para modelos locais                              |
| `LLM_NUM_THREADS` | `8`                                                       | Ajuste à CPU local                                        |

### 🔴 IMPORTANTE - Segurança das API Keys

- **NUNCA** comite o arquivo `.env` (já está no `.gitignore`)
- Se expor uma chave acidentalmente, **revogue imediatamente**:
  - Gemini: https://aistudio.google.com/apikey
  - Groq: https://console.groq.com/keys
- Use `.env.example` como template (sem chaves reais)

### 🧪 Testar Configuração

Antes de rodar o servidor, valide sua configuração:

```bash
python test_llm_config.py
```

Este script verifica:
- ✓ Arquivo `.env` existe
- ✓ API keys configuradas corretamente
- ✓ Formato do modelo correto
- ✓ Conexão com LLM funcionando

**Se encontrar problemas, consulte:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

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
    "criteria": {
      "city": "Joao Pessoa",
      "neighborhood": "Manaira",
      "property_type": "apartamento",
      "bedrooms": 2
    },
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

## Modo "triagem-only" premium 🔒

`TRIAGE_ONLY=true` segue como modo principal: coleta rica + handoff (sem busca/listagem).

### Comportamento atualizado

- ✅ **Pergunta única por mensagem**, com variações naturais e sem repetir campos confirmados.
- ✅ **Campos críticos**: operação, cidade (confirma se inferido), bairros + micro-localização (beira-mar/1-3 quadras), tipo, quartos/suítes mín., vagas mín., orçamento máx./mín., prazo (30d/3m/6m/12m/flex).
- ✅ **Campos importantes** (pergunta 2 extras por padrão): condomínio máx., andar, posição solar, vista, lazer (lista), forma de pagamento/entrada, pet/mobiliado, área mín.
- ✅ **Lead score** a cada mensagem + resumo final (JSON estruturado) para handoff.
- ✅ **Anti-leak**: nada de SEARCH/LIST/REFINE, nem sugerir aumentar orçamento ou bairros.

### Garantias Anti-Leak (7 testes)

- 🚫 **Nunca chama** `tools.search_properties`
- 🚫 **Nunca formata** listagens de imóveis (`format_property_list`)
- 🚫 **Bloqueia** actions SEARCH/LIST mesmo se LLM retornar
- 🚫 **Nunca mostra** preços via `format_price`
- ✅ **`can_search_properties` sempre retorna False**
- ✅ **Handoff automático** ao completar campos

### Schema Canônico de Campos

| Campo                                   | Tipo       | Descrição                                          |
| --------------------------------------- | ---------- | -------------------------------------------------- |
| `intent`                                | string     | comprar/alugar                                     |
| `city`                                  | string     | Cidade (João Pessoa pode vir inferido)             |
| `neighborhood`                          | string     | Bairro(s) desejado(s)                              |
| `micro_location`                        | string     | beira-mar \| 1_quadra \| 2-3_quadras \| >3_quadras |
| `property_type`                         | string     | apartamento/casa/cobertura                         |
| `bedrooms` / `suites`                   | int        | mínimos                                            |
| `parking`                               | int        | vagas mínimas                                      |
| `budget` / `budget_min`                 | int        | teto/piso em R$                                    |
| `timeline`                              | string     | 30d/3m/6m/12m/flexivel                             |
| `condo_max`                             | int        | condomínio máximo                                  |
| `floor_pref` / `sun_pref` / `view_pref` | string     | preferências                                       |
| `leisure_features`                      | list       | piscina, academia, gourmet, playground, etc.       |
| `payment_type` / `entry_amount`         | string/int | forma de pagamento / entrada                       |
| `furnished` / `pet`                     | bool       | mobiliado / aceita pet                             |
| `lead_profile`                          | dict       | name, phone, email                                 |

### Lead scoring & persistência

- `compute_lead_score(state)` → `{temperature: hot|warm|cold, score: 0-100, reasons[]}`; loga `[LEAD_SCORE] ...` em cada mensagem.
- Ao concluir triagem, salva append-only em `data/leads.jsonl` (ou `/mnt/data/leads.jsonl` se existir) com session_id, lead_profile, triage_fields e lead_score.

**Nota:** Em modo normal, `city` e `neighborhood` são agrupados como `location` em alguns contextos.

## Testes (100% Pass Rate - 50/50)

```bash
# Rodar todos os testes
python -m pytest app/tests/ -q

# Rodar com detalhes
python -m pytest app/tests/ -v

# Rodar testes específicos
python -m pytest app/tests/test_triage_anti_leak.py -v
python -m pytest app/tests/test_state_conflicts.py -v

# Demo do agente (requer GROQ_API_KEY)
python demo_ai_agent.py
```

### Suítes de Teste

- **test_flow.py** - Testes de fluxo completo (happy path, edge cases)
- **test_gates.py** - Testes de regras de negócio (can_search, missing_fields)
- **test_handoff_policy.py** - Testes de política de handoff
- **test_triage_mode.py** - Testes do modo TRIAGE_ONLY
- **test_triage_anti_leak.py** ⚡ **NOVO** - 7 testes garantindo isolamento TRIAGE_ONLY
- **test_state_conflicts.py** ⚡ **NOVO** - 9 testes de detecção de conflitos
- **test_single_llm_call.py** - Testes de otimização (1 call LLM/msg)
- **test_fallback_behavior.py** - Testes de fallback em erros
- **test_llm_errors.py** - Testes de normalização de erros

### Garantias de Qualidade

✅ **50 testes passando (100%)**
✅ **Zero regressões** (baseline verificado)
✅ **TRIAGE_ONLY isolation** (anti-leak)
✅ **Conflict detection** (state consistency)
✅ **1 LLM call per message** (performance)
✅ **Fallback resilience** (no crashes)

## Próximos passos sugeridos

- Cache persistente (Redis) para sessões e respostas.
- Métricas de tokens/latência e dashboard simples.
- Integração WhatsApp Cloud API (adaptar payloads e envio).
- Streaming opcional para respostas longas.
