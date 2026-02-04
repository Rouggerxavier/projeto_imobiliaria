# Codex Técnico do Projeto `projeto_imobiliaria`

> Documento técnico **fiel ao código atual** (sem suposições).  
> Cada afirmação aponta para arquivo e, quando faz sentido, função/classe relevante.

## Sumário
- [1) Visão Geral](#sec-1-visao-geral)
- [2) Stack / Dependências / Tecnologias](#sec-2-stack)
- [3) Como Rodar (Local)](#sec-3-como-rodar)
- [4) Arquitetura de Alto Nível (diagrama)](#sec-4-arquitetura)
- [5) Fluxo do Endpoint `/webhook`](#sec-5-webhook)
- [6) Estado / `SessionState` (detalhado)](#sec-6-state)
- [7) Question Bank / Regras de Triagem](#sec-7-question-bank)
- [8) LLM: Prompting e Contratos](#sec-8-llm)
- [9) Lead Scoring (quente/médio/frio)](#sec-9-lead-scoring)
- [10) Lead Router (roteamento de corretores)](#sec-10-lead-router)
- [11) Persistência](#sec-11-persistencia)
- [12) Testes](#sec-12-testes)
- [13) Convenções / Padrões do Projeto](#sec-13-convencoes)
- [14) Troubleshooting](#sec-14-troubleshooting)
- [15) Roadmap Técnico (curto)](#sec-15-roadmap)

---

<a id="sec-1-visao-geral"></a>
## 1) Visão Geral

**O que o projeto faz (3–6 bullets)**
- Backend FastAPI que recebe mensagens via `POST /webhook` e responde texto de atendimento imobiliário (arquivo `app/main.py`, função `webhook`).
- Orquestração de conversa em um ciclo por mensagem: decide → atualiza estado → responde (arquivo `app/agent/controller.py`, função `handle_message`).
- Integração com LLM OpenAI-compatível **ou** fallback determinístico (arquivo `app/agent/llm.py`, função `llm_decide`; regex em `app/agent/extractor.py`).
- Modo **TRIAGE_ONLY** (triagem premium), em que o sistema **não busca nem lista imóveis** e finaliza com resumo + handoff (arquivo `app/agent/controller.py`, bloco `if triage_only:`; regras em `app/agent/rules.py`).
- Busca de imóveis em base local JSON com ranking simples (arquivo `app/agent/tools.py`, função `search_properties`; dados em `app/data/properties.json`).
- Persistência do resultado de triagem em JSONL (arquivo `app/agent/persistence.py`, função `persist_state`; arquivo padrão `data/leads.jsonl`).

**Principais features (confirmadas no código)**
- **TRIAGE_ONLY**: coleta campos críticos + preferências sem listagem/busca (arquivos `app/agent/controller.py`, `app/agent/rules.py`, `app/agent/llm.py`).
- **Lead Scoring** com temperatura `hot|warm|cold` e razões (arquivo `app/agent/scoring.py`).
- **Persistência JSONL** com lock e append-only (arquivo `app/agent/persistence.py`).
- **Anti-leak**: guard-rails bloqueiam `SEARCH/LIST/REFINE` no TRIAGE_ONLY (arquivo `app/agent/llm.py`, função `_validate_decision`, testado em `app/tests/test_triage_anti_leak.py`).
- **Detecção de conflitos** em campos confirmados (arquivo `app/agent/state.py`, método `apply_updates`).
- **Cache + rate-limit** em chamadas LLM (arquivo `app/agent/llm.py`, `_message_cache` e `_rate_limit_until`).

---

<a id="sec-2-stack"></a>
## 2) Stack / Dependências / Tecnologias

**Linguagem e runtime**
- Python 3.x (versão não fixada no repo; ver `requirements.txt`).
- FastAPI + Uvicorn para servidor HTTP (`requirements.txt`; `app/main.py`).
- Pydantic para validação do payload (`app/main.py`, classe `WebhookRequest`).

**Bibliotecas principais (e para quê)**
- `fastapi`: API HTTP (`app/main.py`).
- `uvicorn[standard]`: servidor ASGI (`app/main.py`).
- `pydantic`: schema do webhook (`app/main.py`).
- `python-dotenv`: carrega `.env` (`app/main.py`, `app/agent/llm.py`, scripts).
- `openai`: client OpenAI-compatível (`app/agent/llm.py`).
- `pytest`: testes (`app/tests/*`, `test_edge_cases.py`, `test_triage_completion.py`).

**LangChain/LangGraph**
- **Não usados neste projeto** (confirmado por inspeção de imports em `app/` e `requirements.txt`).

**LLM provider(s)**
- Seleção **por variáveis de ambiente** (arquivo `app/agent/llm.py`):
  - Se `OPENAI_API_KEY` existir → usa OpenAI-compatível com `OPENAI_BASE_URL` e `OPENAI_MODEL`.
  - Senão, se `GROQ_API_KEY` existir → usa Groq com `GROQ_BASE_URL` e `GROQ_MODEL`.
  - Se nenhum → fallback determinístico (sem LLM).
- O `.env` atual aponta para base OpenAI-compatível do Google Gemini, mas isso é apenas configuração (arquivo `.env`).

**Ferramentas de teste**
- Pytest (`requirements.txt` + `app/tests/*`).

**Extras (não estão em `requirements.txt`, mas existem no repo)**
- `frontend.py` usa `streamlit` + `requests` para UI local (arquivo `frontend.py`).

---

<a id="sec-3-como-rodar"></a>
## 3) Como Rodar (Local)

**1) Criar venv e instalar dependências**
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

**2) Configurar `.env`**
> Nota: **não existe** `.env.example` no repositório (arquivo ausente na raiz).  
> O exemplo abaixo foi baseado no `.env` atual, com segredos removidos.

```env
PORT=8000
LOG_LEVEL=info

# === LLM CONFIG ===
OPENAI_API_KEY=CHAVE_AQUI
OPENAI_MODEL=models/gemini-2.0-flash
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai

GROQ_API_KEY=
GROQ_MODEL=
GROQ_BASE_URL=

USE_LLM=true
TRIAGE_ONLY=true

LLM_TIMEOUT=120
LLM_KEEP_ALIVE=30m
LLM_NUM_CTX=2048
LLM_NUM_THREADS=8
LLM_USE_MMAP=true
LLM_PREWARM=true

# Persistência
LEADS_LOG_PATH=data/leads.jsonl

# Outros (presentes no .env, não usados no código atual)
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
ID_CONTA_WPP_BUSINESS=
WHATSAPP_ACCESS_TOKEN=
```
**Fonte:** `.env` + `os.getenv` em `app/main.py`, `app/agent/llm.py`, `app/agent/rules.py`, `app/agent/persistence.py`.

**Tabela de variáveis de ambiente (usadas no código)**
| Variável | Onde é lida | Observação |
|---|---|---|
| `PORT` | `app/main.py` | Porta do Uvicorn |
| `CORRELATION_ID` | `app/main.py` | ID de correlação opcional |
| `OPENAI_API_KEY` | `app/agent/llm.py` | Habilita provider OpenAI-compatível |
| `OPENAI_MODEL` | `app/agent/llm.py` | Modelo OpenAI-compatível |
| `OPENAI_BASE_URL` | `app/agent/llm.py` | Base URL OpenAI-compatível |
| `GROQ_API_KEY` | `app/agent/llm.py` | Habilita provider Groq |
| `GROQ_MODEL` | `app/agent/llm.py` | Modelo Groq |
| `GROQ_BASE_URL` | `app/agent/llm.py` | Base URL Groq |
| `USE_LLM` | `app/agent/llm.py`, `app/agent/unified_llm.py` | Liga/desliga LLM |
| `TRIAGE_ONLY` | `app/agent/llm.py`, `app/agent/rules.py` | Modo triagem-only |
| `LLM_TIMEOUT` | `app/agent/llm.py` | Timeout de chamada |
| `LLM_KEEP_ALIVE` | `app/agent/llm.py` | Ollama local (keep_alive) |
| `LLM_NUM_CTX` | `app/agent/llm.py` | Ollama local (num_ctx) |
| `LLM_NUM_THREADS` | `app/agent/llm.py` | Ollama local (num_thread) |
| `LLM_USE_MMAP` | `app/agent/llm.py` | Ollama local (use_mmap) |
| `LLM_PREWARM` | `app/agent/llm.py` | Prewarm (não é chamado no startup) |
| `LEADS_LOG_PATH` | `app/agent/persistence.py` | Caminho do JSONL |
| `QUESTION_SEED` | `app/agent/rules.py` | Seed estável de perguntas |

**Variáveis presentes no `.env` mas não usadas no código atual**
| Variável | Status |
|---|---|
| `LOG_LEVEL` | Não referenciada nos fontes |
| `WHATSAPP_*` | Não referenciadas nos fontes |

**3) Rodar o servidor**
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
**Fonte:** `README.md` + `app/main.py`.

**4) Endpoints expostos**
- `GET /health` → `{ "status": "ok" }` (arquivo `app/main.py`, função `health`).
- `POST /webhook` → recebe `{session_id, message, name?}` (arquivo `app/main.py`, função `webhook`).

**5) Teste manual (curl)**
```bash
curl -X POST http://localhost:8000/webhook ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"lead-123\",\"message\":\"quero comprar em Manaira\",\"name\":\"Ana\"}"
```
**Resposta (sempre retorna apenas `reply`)**: `{"reply":"..."}`

---

<a id="sec-4-arquitetura"></a>
## 4) Arquitetura de Alto Nível (diagrama)

### Diagrama (Mermaid)
```mermaid
flowchart TD
  A[HTTP POST /webhook] --> B[app/main.py:webhook]
  B --> C[agent/controller.py:handle_message]
  C --> D[agent/ai_agent.py:RealEstateAIAgent.decide]
  D --> E[agent/llm.py:llm_decide]
  E --> F[agent/rules.py + QUESTION_BANK]
  F --> G[agent/state.py:apply_updates]
  G --> H[agent/presenter.py:format/summary]
  H --> I[Resposta JSON {"reply": "..."}]
```

### Papéis por camada (confirmado no código)
- **controller**: orquestra fluxo e retorna resposta (arquivo `app/agent/controller.py`, função `handle_message`).
- **state**: schema, normalização e conflitos (arquivo `app/agent/state.py`).
- **rules**: seleção de perguntas e gates (arquivo `app/agent/rules.py`).
- **extractor**: regex determinístico e enrich (arquivo `app/agent/extractor.py`).
- **presenter**: formata listas e resumo final (arquivo `app/agent/presenter.py`).
- **scoring**: cálculo de lead score (arquivo `app/agent/scoring.py`).
- **persistence**: gravação JSONL (arquivo `app/agent/persistence.py`).
- **tools**: busca e stubs de handoff/agenda (arquivo `app/agent/tools.py`).

### Base local de imóveis
- Arquivo: `app/data/properties.json` (carregado por `tools.load_properties`).
- Total: **46 imóveis** (confirmado por leitura do JSON).
- Campos observados no JSON:
  `id`, `titulo`, `cidade`, `bairro`, `tipo`, `quartos`, `vagas`, `area_m2`,  
  `preco_venda`, `preco_aluguel`, `condominio`, `iptu`, `aceita_pet`, `mobiliado`,  
  `descricao_curta`, `url_fotos`.

**Fonte:** `app/agent/tools.py` + `app/data/properties.json`.

---

<a id="sec-5-webhook"></a>
## 5) Fluxo do Endpoint `/webhook`

**Payload esperado**
```python
class WebhookRequest(BaseModel):
    session_id: str
    message: str
    name: str | None = None
```
**Fonte:** `app/main.py`, classe `WebhookRequest`.

**Passo a passo**
1) Gera `correlation_id` com `CORRELATION_ID` do ambiente ou `os.urandom(8).hex()` (arquivo `app/main.py`).
2) Chama `handle_message(session_id, message, name, correlation_id)` (arquivo `app/main.py`).
3) Retorna **apenas** `{"reply": result["reply"]}` (arquivo `app/main.py`).

**Logs importantes**
- `app/agent/controller.py`: `[INTENT]`, `[CRITERIA]`, `[LEAD_SCORE]`, `[HANDOFF]`, `[PLAN]`.
- `app/agent/llm.py`: `[LLM]`, `[CACHE]`, `[WAIT]`, `[LLM_ERROR]`.

**Fallback em erro LLM**
- `llm_decide` normaliza erro, loga `[LLM_ERROR]`, aplica cooldown e devolve fallback (arquivo `app/agent/llm.py`).
- `controller` prefixa mensagens quando `fallback_reason` existe (arquivo `app/agent/controller.py`).

---

<a id="sec-6-state"></a>
## 6) Estado / `SessionState` (detalhado)

**Arquivo:** `app/agent/state.py`

### Estruturas principais

**`LeadCriteria`**
| Campo | Tipo | Observações |
|---|---|---|
| `city`, `neighborhood`, `micro_location` | `Optional[str]` | `micro_location` é normalizado |
| `property_type` | `Optional[str]` | apartamento/casa/etc. |
| `bedrooms`, `suites`, `parking` | `Optional[int]` | mínimos |
| `budget`, `budget_min` | `Optional[int]` | teto/piso |
| `furnished`, `pet` | `Optional[bool]` | booleanos |
| `urgency`, `financing`, `timeline` | `Optional[str]` | timeline normalizada |
| `condo_max`, `floor_pref`, `sun_pref`, `view_pref` | `Optional[int/str]` | preferências |
| `leisure_features` | `Optional[List[str]]` | itens de lazer |

**`LeadScore`**
| Campo | Tipo | Observações |
|---|---|---|
| `temperature` | `str` | `hot|warm|cold` |
| `score` | `int` | 0–100 |
| `reasons` | `List[str]` | razões do score |

**`SessionState` (campos principais)**
| Campo | Tipo | Observações |
|---|---|---|
| `session_id` | `str` | ID da sessão |
| `intent` | `Optional[str]` | comprar/alugar |
| `stage` | `str` | estágio da conversa |
| `criteria` | `LeadCriteria` | critérios |
| `criteria_status` | `Dict[str,str]` | `confirmed|inferred` |
| `triage_fields` | `Dict[str, Dict]` | `{value,status,source,updated_at}` |
| `lead_profile` | `Dict[str,Any]` | `name`, `phone`, `email` |
| `lead_score` | `LeadScore` | score/temperatura |
| `asked_questions` | `List[str]` | perguntas já feitas |
| `last_question_key` | `Optional[str]` | última pergunta |
| `completed` | `bool` | triagem concluída |
| `fallback_reason` | `Optional[str]` | erro LLM normalizado |
| `last_suggestions` | `List[str]` | IDs sugeridos |
| `human_handoff` | `bool` | transferiu para humano |
| `schedule_requests` | `List[Dict]` | reservado |
| `history` | `List[Dict[str,str]]` | histórico recente |

### `triage_fields` (estrutura interna)
```json
{
  "value": "...",
  "status": "confirmed|inferred",
  "source": "user|llm|default",
  "updated_at": 1700000000.0
}
```
**Fonte:** `SessionState.set_criterion`.

### Aliases e normalização
```python
alias = {
  "operation"   -> "intent",
  "budget_max"  -> "budget",
  "budget_min"  -> "budget_min",
  "bedrooms_min"-> "bedrooms",
  "suites_min"  -> "suites",
  "parking_min" -> "parking",
  "timeline_bucket" -> "timeline",
  "city_confirm" -> "city"
}
```
**Fonte:** `SessionState._apply_alias`.

**Normalizações**
- `budget`, `budget_min`, `bedrooms`, `suites`, `parking`, `condo_max` → `_normalize_numeric`.
- `timeline` → `_normalize_timeline` (`30d|3m|6m|12m|flexivel`).
- `micro_location` → `_normalize_micro_location`.
- `furnished`, `pet` → `_normalize_boolean`.

### Conflitos
```python
conflicts, conflict_values = state.apply_updates(extracted_updates)
```
**Fonte:** `SessionState.apply_updates`.

Regras:
- Campo já `confirmed` + valor diferente → conflito e **não sobrescreve**.
- `intent` tem lógica especial de `override`.

### Respostas curtas (“sim/não”)
```python
if last_question_key == "city_confirm": ...
if last_question_key in {"pet","furnished"}: ...
```
**Fonte:** `_short_reply_updates` em `app/agent/controller.py`.

### Campos críticos (ordem)
```python
CRITICAL_ORDER = ["intent","city","neighborhood","property_type","bedrooms","parking","budget","timeline"]
```
**Fonte:** `app/agent/rules.py`.

**Micro-location**
```python
if micro_status == "inferred" or micro_val == "orla":
    missing.append("micro_location")
```
**Fonte:** `missing_critical_fields` em `app/agent/rules.py`.

---

<a id="sec-7-question-bank"></a>
## 7) Question Bank / Regras de Triagem

### Chaves reais do Question Bank
```text
intent, city, city_confirm, neighborhood, micro_location, property_type,
bedrooms, suites, parking, budget, timeline, budget_min, condo_max,
floor_pref, sun_pref, view_pref, leisure_features, payment_type, lead_name
```
**Fonte:** `app/agent/rules.py`, `QUESTION_BANK`.

### Ordem e seleção
```python
missing_critical_fields(state) -> lista de faltantes (ordem fixa)
next_best_question_key(state) -> primeiro faltante não perguntado
```
**Fonte:** `app/agent/rules.py`.

### Preferências (perguntas extras)
```python
PREFERENCE_ORDER = [
  micro_location, lead_name, budget_min, condo_max, floor_pref, sun_pref,
  view_pref, leisure_features, suites, payment_type, entry_amount,
  furnished, pet, area_min
]
```
**Fonte:** `app/agent/rules.py`.

> Observação: `entry_amount`, `furnished`, `pet`, `area_min` **não têm perguntas no QUESTION_BANK**.

### Variação determinística
```python
_stable_rng(session_id, salt=key)
choose_question(key, state) -> rng.choice(variants)
```
**Fonte:** `app/agent/rules.py`.

### Chaves “alias” citadas no projeto
```text
operation, budget_max, bedrooms_min, suites_min, parking_min, timeline_bucket
```
**Fonte:** `SessionState._apply_alias` (`app/agent/state.py`).

---

<a id="sec-8-llm"></a>
## 8) LLM: Prompting e Contratos

### Onde estão os prompts
**Arquivo:** `app/agent/prompts.py`  
Principais: `INTENT_CLASSIFICATION_PROMPT`, `EXTRACTION_PROMPT`, `DIALOGUE_PLANNING_PROMPT`,  
`HANDOFF_DECISION_PROMPT`, `RESPONSE_GENERATION_PROMPT`, `UNIFIED_DECISION_PROMPT`, `TRIAGE_DECISION_PROMPT`.

### Uso no fluxo atual
```python
RealEstateAIAgent.decide -> llm_decide
```
**Fonte:** `app/agent/ai_agent.py`.

Os métodos `classify_intent`, `extract_criteria`, `plan_next_step`, `should_handoff` existem, mas **não são usados** no fluxo principal (`controller.handle_message` usa apenas `agent.decide`).

### Contrato esperado de `llm_decide`
```json
{
  "intent": "...",
  "criteria": {...},
  "handoff": {"should": true/false, "reason": "..."},
  "plan": {"action": "...", "message": "...", "question_key": "...", "filters": {...}}
}
```
**Fonte:** docstring de `llm_decide` (`app/agent/llm.py`).

### Guard-rails principais
```python
if triage_only: ALLOWED_ACTIONS = {"ASK","HANDOFF","ANSWER_GENERAL","CLARIFY","TRIAGE_SUMMARY"}
if triage_only and action in {"SEARCH","LIST","REFINE","SCHEDULE"} -> força ASK/ANSWER_GENERAL
if triage_only and not missing -> plan.action = "TRIAGE_SUMMARY"
```
**Fonte:** `_validate_decision` em `app/agent/llm.py`.

### Normalização e fallback
- `normalize_llm_error(exc)` converte erros em tipos padronizados (arquivo `app/agent/llm.py`).
- `llm_decide` usa `_get_fallback_decision` em rate limit/timeout/sem key.
- `call_llm` exige resposta JSON (`response_format={"type":"json_object"}`).

### Prewarm
- `prewarm_llm()` existe em `app/agent/llm.py`, mas `app/main.py` **não chama** no startup (função `_startup` retorna imediatamente).

### Arquivo `unified_llm.py`
- Existe e define um prompt compacto, mas **não é importado** em `controller` ou `ai_agent` no fluxo atual.

---

<a id="sec-9-lead-scoring"></a>
## 9) Lead Scoring (quente/médio/frio)

**Implementação:** `app/agent/scoring.py`, função `compute_lead_score`.

**Regras (pontuação incremental)**
- `budget` definido: +20
- `city` definido: +10
- `neighborhood` definido: +15
- `micro_location` definido e != `"orla"`: +10
- `bedrooms >= 3`: +10
- `parking >= 2`: +5
- `intent` em `{comprar, alugar}`: +5
- `timeline`: `30d` +25, `3m` +20, `6m` +10, `12m` +5

```python
score = min(score, 100)
if score >= 70: temperature = "hot"
elif score >= 40: temperature = "warm"
else: temperature = "cold"
```

**Quando calcula**
- Em toda mensagem (arquivo `app/agent/controller.py`, bloco “Aplica lead scoring”).

**Como aparece**
- Log `[LEAD_SCORE]`.
- Persistido em JSONL e incluído no `summary` final (arquivos `app/agent/persistence.py`, `app/agent/presenter.py`).

---

<a id="sec-10-lead-router"></a>
## 10) Lead Router (roteamento de corretores)

**Implementação:** `app/agent/router.py`

### Visão Geral
Sistema determinístico (sem LLM) que atribui leads aos corretores mais adequados baseado em:
- Compatibilidade de operação (compra/aluguel)
- Cobertura geográfica (bairros)
- Faixa de preço
- Especialidades
- Capacidade diária
- Lead score (temperatura)

### Arquivos de Configuração

**1) Cadastro de Corretores**
```
data/agents.json (ou data/agents.example.json)
```

Estrutura de cada corretor:
```json
{
  "id": "agent_maria",
  "name": "Maria Santos",
  "whatsapp": "+5583999991111",
  "active": true,
  "ops": ["rent", "buy"],
  "coverage_neighborhoods": ["Manaíra", "Tambaú", "Cabo Branco"],
  "micro_location_tags": ["beira-mar", "orla", "1_quadra"],
  "price_min": 500000,
  "price_max": 3000000,
  "specialties": ["alto_padrao", "orla"],
  "daily_capacity": 20,
  "priority_tier": "senior"
}
```

**Campos obrigatórios:**
- `id`: identificador único
- `name`: nome do corretor
- `whatsapp`: telefone (formato E.164)
- `active`: `true` para disponível, `false` para inativo
- `ops`: array com `"buy"` e/ou `"rent"`
- `coverage_neighborhoods`: lista de bairros de cobertura (vazio = generalista)
- `micro_location_tags`: tags de micro-localização (`"beira-mar"`, `"1_quadra"`, `"2-3_quadras"`, `">3_quadras"`)
- `price_min`, `price_max`: faixa de preço de atuação
- `specialties`: array de especialidades (ver abaixo)
- `daily_capacity`: limite diário de leads
- `priority_tier`: `"senior"`, `"standard"` ou `"junior"`

**Specialties disponíveis:**
- `"alto_padrao"`: imóveis acima de R$ 900k
- `"familia"`: casas/apartamentos com 3+ quartos
- `"pet_friendly"`: imóveis que aceitam pets
- `"generalista"`: atende qualquer perfil
- `"investimento"`, `"primeira_casa"`, `"luxo"`, etc.

**2) Estatísticas de Atribuição**
```
data/agent_stats.json
```

Rastreamento automático:
```json
{
  "last_reset_date": "2026-02-04",
  "agents": {
    "agent_maria": {
      "assigned_today": 3,
      "last_assigned_at": "2026-02-04T10:30:00Z"
    }
  }
}
```

- Reset diário automático (`assigned_today` volta a 0)
- Escrita atômica com lock (`threading.Lock`)
- Atualização após cada atribuição

### Algoritmo de Pontuação

**Função:** `score_agent(agent, lead_state, stats)`

**Critérios de pontuação:**
| Critério | Pontos | Condição |
|---|---|---|
| Bairro compatível | +30 | Bairro do lead em `coverage_neighborhoods` |
| Micro-localização | +15 | Micro-loc do lead em `micro_location_tags` |
| Faixa de preço | +20 | Budget do lead dentro de `price_min`/`price_max` |
| Hot lead + Senior | +10 | `temperature="hot"` e `priority_tier="senior"` |
| Warm lead + Standard | +5 | `temperature="warm"` e `priority_tier="standard"` |
| Cold lead + Junior | +5 | `temperature="cold"` e `priority_tier="junior"` |
| Specialty alto padrão | +10 | Budget ≥ R$ 900k e `"alto_padrao"` em specialties |
| Specialty família | +10 | Bedrooms ≥ 3 e `"familia"` em specialties |
| Specialty pet | +5 | Pet = true e `"pet_friendly"` em specialties |
| Capacidade atingida | -100 | `assigned_today >= daily_capacity` |
| Sem bairro (generalista) | +5 | Lead sem bairro e corretor generalista |
| Bairro incompatível | -10 | Lead tem bairro mas não está em coverage |
| Preço fora da faixa | -15 | Budget abaixo ou acima da faixa |

**Filtros eliminatórios (score = -1000):**
- `active = false`
- Operação incompatível (ex: lead quer comprar, corretor só aluga)

### Desempate e Round-Robin

Quando múltiplos corretores têm o mesmo score:

1. **Menor `assigned_today`** (balanceamento de carga)
2. **Mais antigo em `last_assigned_at`** (round-robin)
3. **Primeiro na lista** (estável)

**Fonte:** `choose_agent()`, ordenação por `(-score, assigned, last_assigned)`.

### Fallback

Se nenhum corretor for compatível:

1. Tenta corretores `generalistas` (sem cobertura específica ou specialty `"generalista"`)
2. Se não houver, escolhe qualquer agente ativo com menor carga
3. Se nenhum ativo, retorna `None`

**Logs:** `[ROUTER] fallback=generalista` ou `[ROUTER] no_match fallback=default_queue`.

### Integração no Fluxo

**Ponto de execução:** `app/agent/controller.py`, bloco "Triagem concluída".

```python
# Após compute_lead_score()
routing_result = route_lead(state, correlation_id=correlation_id)

if routing_result:
    summary["payload"]["assigned_agent"] = {
        "id": routing_result.agent_id,
        "name": routing_result.agent_name,
        "whatsapp": routing_result.whatsapp,  # se EXPOSE_AGENT_CONTACT=true
        "score": routing_result.score,
        "reasons": routing_result.reasons,
        "fallback": routing_result.fallback
    }
    summary["payload"]["routing"] = {
        "strategy": routing_result.strategy,
        "evaluated_agents_count": routing_result.evaluated_agents_count
    }
```

**Persistência:** O `assigned_agent` é salvo no `leads.jsonl` junto com o resumo.

### UX adicionada (fev/2026)
- Perguntas críticas usam microcopy com motivo+pergunta, uma por vez, variantes estáveis por sessão (`choose_question` / `choose_variant` em `rules.py`).
- Campo novo `intent_stage` (`researching|ready_to_visit|negotiating|unknown`) coletado após bairro+quartos+orçamento; impacta `compute_lead_score`.
- Resumo final traz bullets e frase de transição humanizada (“vou repassar para um corretor… entrar em contato por aqui”), sem prometer prazo.

### Configuração de Privacidade

**Variável de ambiente:** `EXPOSE_AGENT_CONTACT`

```bash
EXPOSE_AGENT_CONTACT=false  # (padrão) não expõe WhatsApp na resposta
EXPOSE_AGENT_CONTACT=true   # expõe WhatsApp e nome do corretor
```

**Comportamento:**
- `false`: Mensagem genérica "um corretor especializado"
- `true`: Mensagem personalizada "o(a) corretor(a) [Nome]"

**Onde é usado:**
- `app/agent/router.py`: filtra `whatsapp` no payload
- `app/agent/presenter.py`: ajusta texto do resumo
- `app/agent/tools.py`: constante `EXPOSE_AGENT_CONTACT`

### Logs

**Formato:**
```
[ROUTER] assigned_agent=agent_maria name=Maria Santos temp=hot score=85 reasons=['neighborhood_match_manaira', ...] correlation=abc123
[ROUTER] no_agents_available correlation=xyz789
[ROUTER] fallback=generalista agent=agent_paula correlation=def456
```

**Campos rastreados:**
- `agent_id` / `agent_name`
- `temp` (temperatura do lead)
- `score` (pontuação final)
- `reasons` (lista de critérios que pontuaram)
- `correlation_id` (rastreabilidade)

### Testes

**Arquivo:** `app/tests/test_router.py`

**Casos cobertos:**
- Carga de agentes do JSON
- Lead hot → corretor senior
- Lead cold → corretor generalista/junior
- Capacidade atingida → escolhe próximo melhor
- Persistência de stats (assigned_today, last_assigned_at)
- Arquivo ausente → fallback gracioso (None)
- Agentes inativos → nunca selecionados
- Specialty "familia" com 3+ quartos
- Specialty "alto_padrao" com budget ≥ 900k
- Round-robin em caso de empate

**Como rodar:**
```bash
python -m pytest app/tests/test_router.py -q
```

### Como Configurar Novos Corretores

1. Editar `data/agents.json` (ou criar a partir de `agents.example.json`)
2. Adicionar novo objeto com estrutura obrigatória
3. Definir `active=true` para ativar
4. Configurar `ops`, `coverage_neighborhoods`, `price_min/max`
5. Opcionalmente adicionar `specialties` e ajustar `priority_tier`
6. Salvar arquivo
7. Reiniciar servidor ou aguardar próximo reload (arquivo é lido a cada roteamento)

**Exemplo de corretor generalista:**
```json
{
  "id": "agent_backup",
  "name": "Backup Geral",
  "whatsapp": "+5583999999999",
  "active": true,
  "ops": ["buy", "rent"],
  "coverage_neighborhoods": [],
  "micro_location_tags": [],
  "price_min": 0,
  "price_max": 999999999,
  "specialties": ["generalista"],
  "daily_capacity": 50,
  "priority_tier": "standard"
}
```

---

<a id="sec-11-persistencia"></a>
## 11) Persistência

**Arquivo:** `app/agent/persistence.py`

**Onde salva**
```python
LEADS_PATH = env(LEADS_LOG_PATH) or "/mnt/data/leads.jsonl" if exists else "data/leads.jsonl"
```

**Formato do JSONL (exemplo real sanitizado)**
```json
{
  "timestamp": 1770035067.7504075,
  "session_id": "anti_leak_4",
  "lead_profile": {"name": null, "phone": null, "email": null},
  "triage_fields": {
    "city": {"value": "Joao Pessoa", "status": "confirmed", "source": "llm", "updated_at": 1770035067.7504075},
    "neighborhood": {"value": "Manaira", "status": "confirmed", "source": "llm", "updated_at": 1770035067.7504075},
    "budget": {"value": 3000, "status": "confirmed", "source": "llm", "updated_at": 1770035067.7504075}
  },
  "lead_score": {"temperature": "hot", "score": 75, "reasons": ["budget_defined", "..."]},
  "completed": true
}
```
**Fonte:** `data/leads.jsonl` (1ª linha, sanitizada) + `persist_state`.

**Lock e atomicidade**
- Usa `threading.Lock()` para escrita serializada (arquivo `app/agent/persistence.py`).

**O que NÃO é salvo**
- Headers HTTP, payload bruto, chaves de API (não existe código persistindo isso).

---

<a id="sec-12-testes"></a>
## 12) Testes

### Como rodar
```bash
python -m pytest app/tests -q
python test_edge_cases.py
python demo_ai_agent.py
```

### Suítes existentes
**`app/tests/`**
- `test_flow.py`: fluxo geral com fallback.
- `test_gates.py`: gates de busca e ordem de faltantes.
- `test_handoff_policy.py`: política de handoff.
- `test_intent.py`: intenção por keywords.
- `test_llm_errors.py`: normalização de erros LLM.
- `test_single_llm_call.py`: 1 chamada por mensagem + cache.
- `test_state_conflicts.py`: conflitos e apply_updates.
- `test_triage_anti_leak.py`: isolamento TRIAGE_ONLY.
- `test_triage_mode.py`: avanço de perguntas + conflitos.
- `test_triage_premium.py`: normalizações, scoring, persistência.
- `test_triage_completion.py`: regressão de triagem completa.

**Raiz**
- `test_edge_cases.py`: cenários manuais/stress.
- `test_triage_completion.py`: teste adicional com stub de agente.

### Como mocks são feitos
```python
patch.object(llm_module, "USE_LLM", False)
patch("agent.extractor.extract_criteria", return_value={...})
```
**Fonte:** diversos testes em `app/tests/`.

---

<a id="sec-13-convencoes"></a>
## 13) Convenções / Padrões do Projeto

### Logs e correlação
- `correlation_id` é gerado por request (arquivo `app/main.py`) e usado nos logs LLM (`app/agent/llm.py`).

### Enum de ações
```python
ALLOWED_ACTIONS = {"ASK","SEARCH","LIST","REFINE","SCHEDULE","HANDOFF","ANSWER_GENERAL","CLARIFY"}
```
**Fonte:** `app/agent/dialogue.py`.

### Nomenclatura de campos
- `city` e `neighborhood` são usados como critérios primários no triage (`app/agent/rules.py`).
- `location` aparece apenas no fallback **não** TRIAGE_ONLY (`app/agent/llm.py`, `_get_fallback_decision`).

### Como adicionar uma nova pergunta/field
1) Adicionar campo em `LeadCriteria` (`app/agent/state.py`).
2) Adicionar alias/normalização em `_apply_alias` / `_normalize_for_field` se necessário.
3) Incluir no `QUESTION_BANK` e/ou `PREFERENCE_ORDER` (`app/agent/rules.py`).
4) Atualizar `missing_critical_fields` se for crítico.
5) Atualizar regex em `extractor.py` e `enrich_with_regex` se for capturado deterministicamente.
6) Atualizar prompts (`app/agent/prompts.py`) se for coletado via LLM.
7) Criar/ajustar testes (`app/tests/*`).

---

<a id="sec-14-troubleshooting"></a>
## 14) Troubleshooting

### 400 BAD_REQUEST / MODEL_NOT_FOUND
- Normalizado por `normalize_llm_error` (arquivo `app/agent/llm.py`).
- Verifique `OPENAI_MODEL`/`OPENAI_BASE_URL` no `.env`.

### 429 Rate Limit / Quota
- `llm_decide` ativa cooldown e fallback (arquivo `app/agent/llm.py`).
- Logs com `[LLM_ERROR]` incluem `retry_after` e `correlation`.

### Loops de pergunta
- Controlado por `asked_questions` e `_avoid_repeat_question` (arquivo `app/agent/controller.py`).

### Erro “UnboundLocalError: question”
- Corrigido no fluxo TRIAGE_ONLY (arquivo `app/agent/controller.py`).

---

<a id="sec-15-roadmap"></a>
## 15) Roadmap Técnico (curto)

Sugestões realistas baseadas no estado atual:
- Persistência em DB (substituir JSONL mantendo o payload).
- Integração WhatsApp (variáveis `WHATSAPP_*` já existem no `.env`, mas não há código).
- Métricas/telemetria por `correlation_id`.
- Cache persistente (Redis) para `_message_cache`.
