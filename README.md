# Agente de IA Imobiliário (FastAPI + LLM, WhatsApp-ready)

Backend de pré-atendimento imobiliário com FastAPI, orquestração determinística + LLM (1 chamada por mensagem), base dummy de 46 imóveis, roteamento para corretores e follow-ups automáticos.

## Visão Rápida
- 1 chamada LLM por turno via `llm_decide()` (cache 5 min, backoff automático em 429/timeout, fallback determinístico se sem key/erro).
- Modo padrão de triagem (`TRIAGE_ONLY=true` no `.env.example`): nunca lista/busca imóveis; coleta dados, calcula score de lead/qualidade e faz handoff + roteamento.
- Guard-rails: enum estrito de ações, validação de filtros, detecção de conflitos, perguntas sem repetição, nome obrigatório antes de concluir.
- Dataset local: `app/data/properties.json` (46 imóveis) e `data/agents.json` (corretores com capacidade diária, cobertura de bairro e faixa de preço).

## Arquitetura e Módulos
- **API** (`app/main.py`): `GET /health`, `POST /webhook` (retorna só `{"reply": ...}`; estado interno é oculto). `CORRELATION_ID` opcional para logs.
- **Controller** (`app/agent/controller.py`): pipeline por mensagem  
  - heurísticas iniciais (reset de sessão pós-conclusão ou 3h inativo, default city=João Pessoa, short “sim/não”/intents, negociação → handoff imediato);  
  - chama `RealEstateAIAgent.decide()` (LLM + regex);  
  - aplica conflitos (`apply_updates`), scores (`compute_lead_score`, `compute_quality_score`), gates de perguntas e finaliza triagem;  
  - persiste JSONL e aciona roteamento + handoff humano.
- **Agente IA** (`ai_agent.py` + `llm.py`): unifica intent + extração + handoff + plano em 1 chamada; auto-detecta provedor (Gemini/OpenAI/OpenRouter/Groq/Ollama). Cache TTL 300s, rate-limit interno, normalização de erros.
- **Estado** (`state.py`): `SessionState` in-memory (`store`) com normalização de números, timeline, booleans; detecção de conflitos por campo confirmando vs novo valor.
- **Regras & Perguntas** (`rules.py`): missing_critical_fields, `next_best_question_key`, microcopy estável por sessão (`QUESTION_SEED`), gate `can_search_properties` (desligado em triagem).
- **Extração** (`extractor.py`): regex/keyword para intent, cidade/bairro (aliases), orçamento, quartos/vagas, pet/mobiliado, micro-location, timeline, lazer.
- **Apresentação** (`presenter.py`): mensagens de handoff, resumo final (`build_summary_payload`), formatação de imóveis (usado só fora do modo triagem).
- **Ferramentas** (`tools.py`): busca ranqueada (tolerância +10% de budget, top 6), cache de imóveis, handoff/schedule stubs. `EXPOSE_AGENT_CONTACT` expõe contato do corretor no resumo.
- **Roteamento** (`router.py`): score por compatibilidade de bairro/micro-localização, faixa de preço, tier, specialty, capacidade diária (reset diário), fallback generalista. Log JSONL opcional (`ROUTING_LOG_PATH`), stats em `data/agent_stats.json`.
- **Persistência** (`persistence.py`):  
  - Triagem append-only em `data/leads.jsonl` (ou `/mnt/data/...` se existir) com lead_score + quality_score + assigned_agent;  
  - Índice por nome em `data/leads_index.json`;  
  - Eventos (HOT_LEAD) em `data/events.jsonl`;  
  - `PERSIST_RAW_TEXT=false` por padrão remove textos livres antes de gravar.
- **Follow-up** (`followup.py`, `scripts/run_followups.py`): identifica leads warm/cold incompletos, gera mensagens curtas (neighborhood, timeline, condo_max, payment_type, micro_location) e registra meta em `data/followups.jsonl`. `--dry-run` para simular.
- **Frontend** (`frontend.py`): chat Streamlit contra `http://localhost:8000/webhook` (mantém `session_id` estável).  
- **Demos**: `demo_ai_agent.py` (requere LLM), `exemplo_conversa.py` (simulação completa).

## Fluxo de Mensagem (TRIAGE_ONLY=true)
1. `handle_message(session_id, message, name?)` carrega estado ou cria novo; reseta se conversa concluída + saudação nova ou 3h ocioso.  
2. Heurísticas: default city=João Pessoa (inferred), “sim/não” confirma último campo, “na verdade...” permite override de intent, “negociar/preço” → handoff direto.  
3. Chama `llm_decide()` com resumo compacto (histórico 6 msgs); se sem LLM ou rate-limited, usa fallback determinístico (regex + regras).  
4. Enrich regex (`enrich_with_regex`), aplica updates com detecção de conflitos (gera pergunta de clarificação).  
5. Recalcula `lead_score` (0–100, hot/warm/cold) e `quality_score` (A–D, completude/confiança).  
6. Pergunta próximo campo crítico (intent, city/confirm, neighborhood, micro_location, property_type, bedrooms, parking, budget, timeline; depois preferências) evitando repetição.  
7. Ao concluir críticos, solicita nome se ausente, então executa roteamento → monta resumo estruturado + handoff humano; marca `completed`, persiste e registra evento HOT_LEAD quando aplicável.

### Modo Normal (TRIAGE_ONLY=false)
- Permite ações `SEARCH|LIST|REFINE|SCHEDULE` se `can_search_properties` (intent + cidade/bairro + tipo + budget).  
- Usa `tools.search_properties` e `presenter.format_property_list`; fora do modo normal, guard-rails no `llm_decide` convertem ações proibidas em `ASK/ANSWER_GENERAL`.

## Endpoints
- `GET /health` → `{"status": "ok"}`.  
- `POST /webhook` body:  
  ```json
  { "session_id": "lead-123", "message": "quero alugar apto em Manaíra até 3 mil", "name": "Maria" }
  ```  
  Resposta: `{"reply": "..."}`

## Setup Rápido
```bash
python -m venv .venv
.\.venv\Scripts\activate          # PowerShell (Windows) | source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # preenche depois
```

### Escolha do provedor LLM
- **Gemini (OpenAI compat, default do template)**  
  - Gere key em https://aistudio.google.com/apikey  
  - `OPENAI_API_KEY`, `OPENAI_MODEL=gemini-2.5-flash`, `OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`
- **Groq (recomendado pela estabilidade)**  
  - `GROQ_API_KEY`, `GROQ_MODEL=llama-3.3-70b-versatile`; comente as linhas `OPENAI_*`.
- **Ollama local**  
  ```env
  OPENAI_BASE_URL=http://localhost:11434/v1
  OPENAI_MODEL=llama3.2
  OPENAI_API_KEY=ollama
  LLM_TIMEOUT=120
  ```
- Sem key ou `USE_LLM=false` → fallback determinístico continua funcionando.

### Testar configuração LLM
```bash
python test_llm_config.py   # valida .env, formato do modelo e conecta no provedor
```
Erros comuns estão em `TROUBLESHOOTING.md`.

## Variáveis de Ambiente Importantes
| Chave | Default (template) | Uso |
| --- | --- | --- |
| `USE_LLM` | `true` | Desliga LLM se `false` (usa regras/regex). |
| `TRIAGE_ONLY` | `true` | Desativa SEARCH/LIST/REFINE/SCHEDULE; mantém só triagem + resumo. |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | – | Gemini/OpenAI/OpenRouter. |
| `GROQ_API_KEY` / `GROQ_MODEL` / `GROQ_BASE_URL` | – | Alternativa Groq. |
| `LLM_TIMEOUT` | `120` | 30s remoto; sugere 120s local. |
| `LLM_KEEP_ALIVE`, `LLM_NUM_CTX`, `LLM_NUM_THREADS`, `LLM_USE_MMAP`, `LLM_PREWARM` | – | Tunables para LLM local. |
| `PORT` | `8000` | Porta do FastAPI. |
| `EXPOSE_AGENT_CONTACT` | `false` | Se `true`, inclui contato do corretor no handoff/summary. |
| `LEADS_LOG_PATH`, `LEADS_INDEX_PATH`, `EVENTS_PATH` | auto | Redirecionam persistência (padrão: `data/*.jsonl`). |
| `ROUTING_LOG_PATH` | `data/routing_log.jsonl` | Log JSONL do roteamento (opcional). |
| `PERSIST_RAW_TEXT` | `false` | Se `true`, grava `raw_text` dos campos. |
| `FOLLOWUP_META_PATH` | `data/followups.jsonl` | Registro de follow-ups enviados. |
| `QUESTION_SEED` | – | Torna variantes de pergunta reproduzíveis. |

## Rodar
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- Frontend (opcional): `streamlit run frontend.py` → usar chat no browser.  
- Demos: `python demo_ai_agent.py` (exige LLM), `python exemplo_conversa.py`.  
- Follow-ups: `python scripts/run_followups.py --dry-run --limit 5`.

## Dados e Persistência
- **Imóveis**: `app/data/properties.json` (46 itens: id, título, cidade, bairro, tipo, quartos, vagas, área, preços venda/aluguel, condomínio, IPTU, pet, mobiliado, descrição, fotos). Carregado em cache na importação.  
- **Corretores**: `data/agents.json` (ops buy/rent, bairros, micro_location tags, faixa de preço, specialties, capacidade diária, tier). Stats em `data/agent_stats.json` (reset diário).  
- **Leads/Eventos**: `data/leads.jsonl`, `data/leads_index.json`, `data/events.jsonl`, `data/routing_log.jsonl` (opcional). Hot leads geram evento `HOT_LEAD`.

## Qualidade, Segurança e Anti-Leak
- Ações permitidas em triagem: `ASK|CLARIFY|ANSWER_GENERAL|HANDOFF|TRIAGE_SUMMARY`; guard-rail impede SEARCH/LIST/REFINE/SCHEDULE quando `TRIAGE_ONLY` ou sem critérios mínimos.  
- Enum de ações e filtros validados (`dialogue.py`), filtros sanitizados antes de usar.  
- Detecção de conflitos: campos confirmados não são sobrescritos sem pergunta de clarificação.  
- Critérios confirmados vs inferidos armazenados com `status` + `raw_text` (opcional).  
- Rate-limit interno e cooldown quando 429; cache de decisão por mensagem+estado (5 min).  
- Sem persona inventada; tom profissional curto; evita repetir campos já perguntados; saudação automática quando pertinente.  
- `should_handoff_to_human` via LLM + fallback keywords para negociação/visita/reclamação/jurídico/pedido humano/alta intenção.  
- Session reset após conclusão + nova saudação com intenção ou 3h ocioso.

## Lead Scoring, Quality Score e Roteamento
- **Lead Score** (`scoring.py`): pondera orçamento, cidade/bairro, micro_location, quartos/vagas, intent, timeline e intent_stage → temperatura hot/warm/cold e score 0-100.
- **Quality Score** (`quality.py`): completude dos críticos, confirmed vs inferred, dealbreakers (micro_location ambígua, condo_max ausente em budget alto, payment_type em compra), conflitos recentes → grade A–D + confidence/completeness.
- **Quality Gate** (`quality_gate.py`): controle de handoff baseado em quality_score. Bloqueia triagem prematura (grade C/D) e faz 1–3 perguntas cirúrgicas para melhorar dados antes do handoff. Detecta recusas e evita repetir perguntas. Configurável via constantes `MAX_QUALITY_GATE_TURNS` (default: 3) e `QUALITY_GATE_MIN_SCORE` (default: 70).
- **SLA Policy** (`sla.py`): classifica leads em HOT/WARM/COLD (thresholds: 80/50) e dispara ações automáticas: HOT → resposta imediata + roteamento prioritário + evento HOT_LEAD; WARM → handoff normal; COLD → handoff ou nutrição. Configurável via `SLA_HOT_THRESHOLD` e `SLA_WARM_THRESHOLD`.
- **Roteamento** (`router.py`): score por bairro/micro-location/price_range/specialties/lead temperature/tier; penaliza capacidade diária excedida (exceto HOT com `priority=true`); fallback generalista. Pode expor contato se `EXPOSE_AGENT_CONTACT=true`.

## Budget Range Support - Faixas de Orçamento

O sistema agora detecta e interpreta faixas de orçamento automaticamente, evitando falsos conflitos e permitindo que usuários especifiquem `budget_min` e `budget_max` de forma natural.

### Padrões Suportados

**Ranges Explícitos:**
- `"entre 800 mil e 1.2 milhão"` → min=800k, max=1.2M
- `"de 900k a 1.1m"` → min=900k, max=1.1M
- `"800 mil a 1 milhão"` → min=800k, max=1M
- `"700 mil até 1.2 milhão"` → min=700k, max=1.2M
- `"900 mil - 1.5 milhão"` → min=900k, max=1.5M (hífen)
- `"850k ~ 1.2m"` → min=850k, max=1.2M (til)

**Apenas Máximo:**
- `"até 1 milhão"` → max=1M
- `"máximo 900k"` → max=900k
- `"teto de 1.5 milhão"` → max=1.5M

**Apenas Mínimo:**
- `"a partir de 700 mil"` → min=700k
- `"mínimo 800 mil"` → min=800k
- `"pelo menos 600k"` → min=600k

**Range Implícito:**
- `"busco algo por 800 mil mas aceito até 1 milhão"` → min=800k, max=1M
- Múltiplos valores na mesma mensagem são automaticamente interpretados como range

### Formatos Monetários Aceitos
- `"800 mil"`, `"1 milhão"`, `"1.2 milhões"`
- `"900k"`, `"1.1m"`, `"1.5mi"`
- `"R$ 1.200.000"` (formato PT-BR com pontos)
- `"1 milhão e 200 mil"` (formato composto)

### Detecção Inteligente de Conflitos

O sistema **não** marca como conflito quando:
- Usuário fornece um range válido (min <= max) na mesma mensagem
- Valores estão dentro de um range já estabelecido

O sistema **marca como conflito** quando:
- Novo valor incompatível com range existente (ex: range 800k-1.2M → usuário diz "máximo 600k")
- Valores contraditórios em mensagens diferentes (ex: "máximo 1M" → depois "máximo 500k")

### Exemplo de Fluxo
```
User: "Quero alugar apartamento entre 800 mil e 1 milhão e 200 mil"
Agent: ✓ Detecta range: budget_min=800k, budget_max=1.2M (sem conflito)
Agent: "Perfeito — então seu orçamento fica entre R$ 800.000 e R$ 1.200.000, certo?"

User: "Na verdade meu máximo é 600 mil"
Agent: ✗ Detecta conflito (600k < 800k existing min)
Agent: "Aqui ficou registrado que seu orçamento mínimo é R$ 800.000 e máximo R$ 1.200.000.
       Agora você disse R$ 600.000. Isso fica fora da faixa. Pode confirmar qual é o orçamento correto?"
```

### Armazenamento

Ranges são persistidos com ambos os valores:
```json
{
  "budget_min": 800000,
  "budget_max": 1200000,
  "budget_is_range": true
}
```

No resumo final, exibido como:
- `"Orçamento: R$ 800.000 a R$ 1.200.000"` (range completo)
- `"Orçamento máx.: R$ 1.000.000"` (apenas max)
- `"Orçamento mín.: R$ 700.000"` (apenas min)

### Testes

Execute os testes específicos de budget range:
```bash
pytest app/tests/test_budget_range.py -v
```

26 cenários cobertos incluindo ranges explícitos, implícitos, valores únicos, e detecção de conflitos reais.

## Quality Gate - Controle Inteligente de Handoff

O Quality Gate é um mecanismo que previne handoffs prematuros quando o quality_score é baixo (C/D), fazendo perguntas cirúrgicas para melhorar a qualidade dos dados antes de transferir para o corretor.

### Como Funciona
1. **Verificação de Qualidade**: Quando todos os campos críticos estão preenchidos, o sistema calcula o `quality_score` (grade A-D).
2. **Decisão de Handoff**:
   - Se grade **A ou B** (score ≥ 70): handoff permitido imediatamente.
   - Se grade **C ou D** (score < 70): quality gate identifica gaps específicos e faz 1–3 perguntas adicionais.
   - Após **3 perguntas de gate**: handoff permitido mesmo com score baixo (evita loop infinito).

### Gaps Identificados (prioridade decrescente)
1. **Dealbreakers** (campos críticos que bloqueiam qualidade):
   - `payment_type` faltando (para compra)
   - `condo_max` faltando (budget > 500k)
   - `micro_location` ambígua (valor "orla" ou inferred)
2. **Campos críticos missing** (seguindo CRITICAL_ORDER)
3. **Campos ambíguos** (ex: micro_location "orla")
4. **Campos com baixa confiança** (status "inferred")
5. **Conflitos não resolvidos**

### Detecção de Recusas
O sistema detecta quando o usuário recusa informar um campo (ex: "não sei", "prefiro não informar", "tanto faz") e:
- Marca o campo como recusado no estado (`field_refusals`)
- Não repete a pergunta daquele campo
- Passa para o próximo gap relevante

### Configuração
Ajuste os thresholds editando as constantes em `app/agent/quality_gate.py`:
```python
MAX_QUALITY_GATE_TURNS = 3       # Máximo de perguntas extras (default: 3)
QUALITY_GATE_MIN_SCORE = 70      # Score mínimo para bypass (default: 70, equivalente a grade B)
```

### Exemplo de Fluxo
```
1. Usuário fornece dados básicos (intent, bairro, quartos, orçamento)
2. Quality score calculado: C (70 pontos) - faltam dealbreakers
3. Quality gate identifica gap: payment_type faltando (compra)
4. Sistema pergunta: "Como pretende pagar? Financiamento, à vista, FGTS ou misto?"
5. Usuário responde: "financiamento"
6. Quality score recalculado: B (85 pontos)
7. Quality gate permite handoff → roteamento para corretor
```

## SLA Policy - Fluxo Diferenciado por Lead Score

O sistema classifica leads automaticamente em **HOT/WARM/COLD** baseado no `lead_score` (0-100) e dispara ações diferenciadas:

### Classificação e Thresholds

| Classe | Score     | SLA        | Ação                                                    |
|--------|-----------|------------|---------------------------------------------------------|
| **HOT**    | >= 80     | Immediate  | Resposta imediata, roteamento prioritário, evento HOT_LEAD |
| **WARM**   | 50-79     | Normal     | Handoff padrão para corretor                            |
| **COLD**   | < 50      | Normal/Nurture | Handoff normal (quality A/B) ou nutrição (quality C/D) |

**Configuração:** Ajuste os thresholds via variáveis de ambiente:
```bash
SLA_HOT_THRESHOLD=80    # Score mínimo para HOT (default: 80)
SLA_WARM_THRESHOLD=50   # Score mínimo para WARM (default: 50)
```

### Ações por Classe

#### HOT Leads (Score >= 80)
1. **Mensagem imediata ao cliente**: "Já acionei [corretor] agora e ele deve te chamar em instantes."
2. **Roteamento prioritário**:
   - Ignora limite de capacidade diária do corretor (prioriza match de qualidade)
   - Pequena penalização (-5 pontos) se corretor estiver no limite, mas não bloqueia
3. **Evento HOT_LEAD completo** em `events.jsonl`:
   ```json
   {
     "type": "HOT_LEAD",
     "lead_id": "abc123",
     "session_id": "lead-456",
     "timestamp": 1234567890.0,
     "lead_score": 85,
     "lead_class": "HOT",
     "quality_grade": "A",
     "sla": "immediate",
     "lead_profile": {"name": "...", "phone": "...", "email": "..."},
     "criteria": {"intent": "comprar", "neighborhood": "Manaíra", ...},
     "assigned_agent": {"id": "agent_senior", "name": "Maria", ...}
   }
   ```
4. **Proteção contra duplicata**: Evento HOT_LEAD só é emitido uma vez por `session_id`

#### WARM Leads (Score 50-79)
- **Mensagem padrão**: "Entendi seu perfil! Vou repassar para [corretor], que vai entrar em contato em breve."
- **Roteamento normal**: Respeita capacidade diária e scoring padrão
- Sem evento especial (apenas handoff normal)

#### COLD Leads (Score < 50)
- **Qualidade boa (A/B)**: Handoff normal para corretor
  - Mensagem: "Anotei suas preferências. Um corretor vai avaliar as opções e entrar em contato."
- **Qualidade baixa (C/D)**: Nutrição/follow-up
  - Mensagem: "Anotei suas preferências. Vou te manter informado sobre opções que se encaixem no seu perfil."
  - `sla_type = "nurture"` marcado no registro

### Persistência

Cada lead salvo em `data/leads.jsonl` inclui:
```json
{
  "lead_id": "...",
  "lead_class": "HOT",         // HOT/WARM/COLD
  "sla": "immediate",           // immediate/normal/nurture
  "priority": true,             // true para HOT, false para outros
  "last_action": "hot_handoff", // hot_handoff/warm_handoff/cold_handoff/cold_nurture
  "lead_score": {...},
  "quality_score": {...},
  ...
}
```

### Exemplo de Fluxo HOT

```
1. Lead fornece: Manaíra, 3 quartos, 2 vagas, 800k, timeline 30d
2. lead_score calculado: 85 (HOT)
3. SLA Policy:
   - Classifica: HOT
   - Ação: immediate, priority=true
   - Mensagem: "Já acionei Maria agora e ela deve te chamar em instantes."
4. Roteamento prioritário:
   - Ignora capacidade diária de Maria
   - Atribui lead para Maria (melhor match)
5. Evento HOT_LEAD salvo em events.jsonl
6. Flag hot_lead_emitted=true (proteção contra duplicata)
```

## Testes
- Unitários/integração em `app/tests/` (23 arquivos: triage_only/anti-leak, conflitos, gates, quality_gate, sla, followup, router, intent, handoff, LLM errors, etc).
- Testes raiz: `test_router_integration.py`, `test_edge_cases.py`, `test_triage_completion_legacy.py`, `test_llm_config.py`.
- Rodar:
  ```bash
  python -m pytest app/tests -q
  python -m pytest app/tests/test_quality_gate.py -v  # testes específicos do quality gate
  python -m pytest app/tests/test_sla.py -v           # testes específicos do SLA policy
  python -m pytest test_router_integration.py -q       # integração triagem + roteamento
  python test_llm_config.py                             # valida .env + conexão LLM
  ```

## Próximos Passos Sugeridos
- Persistir sessões (Redis) para múltiplas instâncias.
- Métricas de tokens/latência e dashboard simples.
- Plug WhatsApp Cloud API (adaptar payload e headers).
- Streaming opcional para respostas longas.

