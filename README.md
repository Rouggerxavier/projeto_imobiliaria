# 🏠 Projeto Imobiliária — Atendente Inteligente com IA

> Chatbot de atendimento imobiliário que conduz uma triagem consultiva com o cliente, classifica o lead por temperatura (quente/morno/frio) e encaminha automaticamente para o corretor mais adequado.

---

## 📌 O que este projeto faz (em linguagem simples)

Imagine que uma imobiliária recebe dezenas de mensagens por dia: "quero um apartamento em Manaíra", "procuro casa para alugar", etc. Responder a cada uma manualmente é cansativo e lento.

Este projeto é um **assistente virtual inteligente** que:

1. **Recebe a mensagem** do cliente via API (podendo ser integrado ao WhatsApp, site, etc.)
2. **Faz perguntas inteligentes** para entender o que o cliente quer (cidade, bairro, tipo de imóvel, número de quartos, orçamento, prazo)
3. **Classifica o lead** como `quente`, `morno` ou `frio` com base nas respostas
4. **Escolhe o corretor certo** da equipe para atender aquele perfil específico
5. **Salva o histórico** da conversa em arquivo para análise posterior

Tudo isso sem precisar de um humano na triagem inicial.

---

## 🗂️ Estrutura de Pastas

```
projeto_imobiliaria/
│
├── app/                        # Código principal da aplicação
│   ├── main.py                 # Ponto de entrada da API (FastAPI)
│   ├── faq.py                  # Respostas a perguntas frequentes
│   │
│   ├── agent/                  # Núcleo do agente de IA
│   │   ├── controller.py       # Orquestrador central do fluxo de conversa
│   │   ├── ai_agent.py         # Agente de IA (interface com o LLM)
│   │   ├── llm.py              # Comunicação com a IA (OpenAI/Groq/fallback)
│   │   ├── state.py            # Dados da sessão do cliente
│   │   ├── rules.py            # Regras de triagem e banco de perguntas
│   │   ├── extractor.py        # Extração de dados da mensagem (regex)
│   │   ├── scoring.py          # Cálculo de score do lead (quente/morno/frio)
│   │   ├── router.py           # Roteamento: escolhe o corretor ideal
│   │   ├── presenter.py        # Formata as respostas enviadas ao cliente
│   │   ├── persistence.py      # Salva dados do lead em arquivo
│   │   ├── prompts.py          # Textos/instruções enviados à IA
│   │   ├── tools.py            # Busca de imóveis na base local
│   │   ├── dialogue.py         # Definição de ações possíveis do agente
│   │   ├── quality.py          # Verificação de qualidade das respostas
│   │   ├── quality_gate.py     # Portão de qualidade (valida critérios)
│   │   ├── sla.py              # Controle de tempo de atendimento (SLA)
│   │   ├── followup.py         # Mensagens de acompanhamento pós-triagem
│   │   ├── unified_llm.py      # Prompt compacto alternativo para o LLM
│   │   └── intent.py           # Detecção de intenção (comprar/alugar)
│   │
│   ├── routes/                 # Rotas adicionais da API
│   ├── services/               # Serviços auxiliares
│   ├── core/                   # Configurações e utilitários base
│   └── tests/                  # Testes automatizados
│
├── data/                       # Dados persistidos
│   ├── leads.jsonl             # Histórico de leads (append-only)
│   ├── agents.json             # Cadastro de corretores
│   └── agent_stats.json        # Estatísticas de atribuição diária
│
├── app/data/
│   └── properties.json         # Base de 46 imóveis disponíveis
│
├── frontend.py                 # Interface web local (Streamlit)
├── requirements.txt            # Dependências Python
├── .env                        # Configurações e chaves de API (não versionar)
│
├── test_edge_cases.py          # Testes de casos extremos
├── test_endpoints.py           # Testes dos endpoints da API
├── test_router_integration.py  # Testes de integração do roteador
├── demo_ai_agent.py            # Script de demonstração do agente
└── codex.md                    # Documentação técnica detalhada (para devs)
```

---

## 🔧 Stack Tecnológica

| Tecnologia | Para que serve |
|---|---|
| **Python 3.x** | Linguagem principal do projeto |
| **FastAPI** | Framework web para criar a API HTTP |
| **Uvicorn** | Servidor que executa a aplicação FastAPI |
| **Pydantic** | Validação dos dados recebidos pela API |
| **OpenAI SDK** | Biblioteca para comunicar com modelos de IA |
| **python-dotenv** | Carrega variáveis de ambiente do arquivo `.env` |
| **Pytest** | Framework de testes automatizados |
| **Streamlit** | Interface web para testes locais (opcional) |

### Modelos de IA suportados (configuráveis via `.env`)

O projeto suporta diferentes provedores de IA — basta configurar as variáveis de ambiente:

| Provedor | Variável necessária |
|---|---|
| **Google Gemini** (padrão atual) | `OPENAI_API_KEY` + `OPENAI_BASE_URL` apontando para o Gemini |
| **Groq** | `GROQ_API_KEY` |
| **OpenAI** | `OPENAI_API_KEY` |
| **Sem IA (fallback)** | Nenhuma chave — usa regras determinísticas |

---

## 🏗️ Arquitetura — Como o sistema funciona

### Visão simplificada do fluxo

```
Cliente envia mensagem
        │
        ▼
[API - /webhook]  ← app/main.py
        │
        ▼
[Controller]  ← app/agent/controller.py
   ┌────┴────────────────────────────────────┐
   │  1. Extrai dados da mensagem (regex)    │  ← extractor.py
   │  2. Chama a IA para decidir ação        │  ← llm.py / ai_agent.py
   │  3. Atualiza estado da sessão           │  ← state.py
   │  4. Verifica se triagem acabou          │  ← rules.py
   │  5. Calcula score do lead               │  ← scoring.py
   │  6. (Se completo) Escolhe corretor      │  ← router.py
   │  7. Salva lead no arquivo               │  ← persistence.py
   │  8. Formata resposta para o cliente     │  ← presenter.py
   └─────────────────────────────────────────┘
        │
        ▼
Resposta: {"reply": "...mensagem para o cliente..."}
```

### Os arquivos mais importantes

#### `app/main.py` — A porta de entrada
Define os 2 endpoints da API:
- `GET /health` — verifica se o servidor está rodando
- `POST /webhook` — recebe mensagens e retorna respostas

#### `app/agent/controller.py` — O cérebro do sistema
É o arquivo mais importante. Ele orquestra tudo: recebe a mensagem, chama a IA, atualiza o estado, calcula score, aciona o roteador e devolve a resposta. Contém a função `handle_message`.

#### `app/agent/state.py` — A memória da conversa
Armazena tudo que o sistema sabe sobre o cliente durante a conversa:
- Intenção (comprar ou alugar)
- Critérios buscados (cidade, bairro, quartos, orçamento, etc.)
- Score do lead (quente/morno/frio)
- Histórico de perguntas já feitas

#### `app/agent/rules.py` — O roteiro da triagem
Contém as perguntas que o bot faz, em que ordem e quando. Define quais campos são obrigatórios (campos críticos) e quais são preferências extras.

**Campos críticos (obrigatórios):**
`intenção → cidade → bairro → tipo de imóvel → quartos → vagas → orçamento → prazo`

#### `app/agent/llm.py` — A ponte com a IA
Envia as mensagens para o modelo de IA e interpreta as respostas. Possui cache (evita chamar a IA com a mesma pergunta duas vezes) e proteção contra erros de quota.

#### `app/agent/scoring.py` — O classificador de leads
Calcula uma pontuação de 0 a 100 e classifica o lead:

| Temperatura | Pontuação | Significa |
|---|---|---|
| 🔴 **Quente (hot)** | ≥ 70 | Pronto para comprar/alugar em breve |
| 🟡 **Morno (warm)** | 40–69 | Interessado mas sem urgência |
| 🔵 **Frio (cold)** | < 40 | Ainda pesquisando, sem decisão |

**Como os pontos são somados:**
- Budget definido: +20 pts
- Cidade informada: +10 pts
- Bairro informado: +15 pts
- Micro-localização: +10 pts
- 3+ quartos: +10 pts
- 2+ vagas: +5 pts
- Intenção clara: +5 pts
- Prazo de 30 dias: +25 pts | 3 meses: +20 pts | 6 meses: +10 pts

#### `app/agent/router.py` — O despachante de corretores
Após a triagem, escolhe automaticamente o melhor corretor para o lead com base em:
- Compatibilidade de operação (compra vs aluguel)
- Bairros de cobertura do corretor
- Faixa de preço de atuação
- Especialidades (alto padrão, família, pet-friendly, etc.)
- Capacidade diária disponível
- Temperatura do lead (leads quentes vão para corretores sênior)

#### `app/agent/persistence.py` — O arquivo de leads
Salva cada triagem concluída no arquivo `data/leads.jsonl` em formato JSON. Usa lock de thread para evitar conflitos em múltiplos acessos simultâneos.

---

## 🚀 Como rodar o projeto localmente

### Pré-requisitos
- Python 3.10 ou superior instalado
- Chave de API de algum provedor de IA (Google Gemini, Groq ou OpenAI)

### Passo 1 — Criar ambiente virtual e instalar dependências

```bash
python -m venv .venv

# Windows:
.\.venv\Scripts\activate

# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
```

### Passo 2 — Configurar o arquivo `.env`

Crie um arquivo `.env` na raiz do projeto com o seguinte conteúdo (ajuste com suas chaves):

```env
PORT=8000

# === Provedor de IA (escolha um) ===

# Opção 1: Google Gemini (recomendado)
OPENAI_API_KEY=SUA_CHAVE_GEMINI_AQUI
OPENAI_MODEL=gemini-2.5-flash
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

# Opção 2: Groq
# GROQ_API_KEY=SUA_CHAVE_GROQ_AQUI
# GROQ_MODEL=llama-3.1-8b-instant

# === Configurações do agente ===
USE_LLM=true
TRIAGE_ONLY=true

# === Persistência ===
LEADS_LOG_PATH=data/leads.jsonl
```

### Passo 3 — Iniciar o servidor

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

O servidor estará disponível em: `http://localhost:8000`

### Passo 4 — Testar com uma mensagem

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"lead-001\",\"message\":\"quero comprar um apartamento em Manaíra\",\"name\":\"João\"}"
```

**Resposta esperada:**
```json
{"reply": "Olá João! Que ótimo que você está procurando um imóvel em Manaíra! Para te ajudar melhor, você prefere comprar ou alugar?"}
```

### Passo 5 (opcional) — Interface visual

```bash
pip install streamlit
streamlit run frontend.py
```

---

## 🧪 Testes

```bash
# Rodar todos os testes automatizados
python -m pytest app/tests -q

# Testes de casos especiais
python test_edge_cases.py

# Demonstração do agente
python demo_ai_agent.py
```

### O que cada arquivo de teste cobre

| Arquivo | O que testa |
|---|---|
| `app/tests/test_flow.py` | Fluxo completo da conversa |
| `app/tests/test_gates.py` | Ordem e seleção das perguntas |
| `app/tests/test_state_conflicts.py` | Conflitos quando o cliente muda de ideia |
| `app/tests/test_triage_anti_leak.py` | Garante que no modo triagem não busca imóveis |
| `app/tests/test_scoring.py` | Cálculo de pontuação do lead |
| `app/tests/test_router.py` | Roteamento de corretores |
| `app/tests/test_llm_errors.py` | Comportamento quando a IA falha ou atinge limite |
| `test_edge_cases.py` | Casos extremos e estresse |
| `test_router_integration.py` | Integração completa do roteador |

---

## 👥 Cadastro de Corretores

Os corretores são cadastrados no arquivo `data/agents.json`. Exemplo de um corretor:

```json
{
  "id": "corretor_joao",
  "name": "João Silva",
  "whatsapp": "+5583999991234",
  "active": true,
  "ops": ["buy", "rent"],
  "coverage_neighborhoods": ["Manaíra", "Tambaú", "Cabo Branco"],
  "micro_location_tags": ["beira-mar", "orla"],
  "price_min": 300000,
  "price_max": 2000000,
  "specialties": ["familia", "pet_friendly"],
  "daily_capacity": 15,
  "priority_tier": "senior"
}
```

**Especialidades disponíveis:**
- `alto_padrao` — imóveis acima de R$ 900 mil
- `familia` — imóveis com 3+ quartos
- `pet_friendly` — imóveis que aceitam animais
- `generalista` — atende qualquer perfil
- `investimento`, `primeira_casa`, `luxo`

---

## ⚙️ Variáveis de Ambiente Principais

| Variável | Descrição | Default |
|---|---|---|
| `PORT` | Porta do servidor | `8000` |
| `USE_LLM` | Liga/desliga a IA (`true`/`false`) | `true` |
| `TRIAGE_ONLY` | Modo apenas triagem (sem busca de imóveis) | `true` |
| `OPENAI_API_KEY` | Chave de API OpenAI/Gemini | — |
| `OPENAI_MODEL` | Modelo a usar | — |
| `OPENAI_BASE_URL` | URL base do provedor | — |
| `GROQ_API_KEY` | Chave de API Groq (alternativa) | — |
| `LLM_TIMEOUT` | Timeout das chamadas à IA (segundos) | `120` |
| `LEADS_LOG_PATH` | Caminho do arquivo de leads | `data/leads.jsonl` |
| `EXPOSE_AGENT_CONTACT` | Expõe WhatsApp do corretor na resposta | `false` |

---

## 📊 Formato dos Dados Salvos (leads.jsonl)

Cada linha do arquivo `data/leads.jsonl` é um JSON com a triagem completa:

```json
{
  "timestamp": 1770035067.75,
  "session_id": "lead-001",
  "lead_profile": {"name": "João", "phone": null, "email": null},
  "triage_fields": {
    "city":         {"value": "João Pessoa", "status": "confirmed", "source": "user"},
    "neighborhood": {"value": "Manaíra",     "status": "confirmed", "source": "user"},
    "budget":       {"value": 800000,        "status": "confirmed", "source": "llm"}
  },
  "lead_score": {
    "temperature": "hot",
    "score": 75,
    "reasons": ["budget_defined", "neighborhood_match", "timeline_30d"]
  },
  "assigned_agent": {
    "id": "corretor_joao",
    "name": "João Silva",
    "score": 85
  },
  "completed": true
}
```

---

## 🔒 Modo TRIAGE_ONLY

Quando `TRIAGE_ONLY=true` (padrão recomendado), o agente:

- ✅ Faz perguntas consultivas ao cliente
- ✅ Extrai e valida critérios
- ✅ Calcula score e encaminha para corretor
- ❌ **NÃO** lista imóveis disponíveis
- ❌ **NÃO** faz buscas na base de imóveis
- ❌ **NÃO** marca visitas diretamente

Esse modo é ideal para imobiliárias que querem qualificar o lead antes de envolvê-lo com o catálogo.

---

## 📁 Documentação técnica

Para informações técnicas detalhadas (com referências linha-a-linha ao código), consulte o arquivo [`codex.md`](./codex.md).

---

## 📋 Resumo rápido dos fluxos

```
MODO TRIAGE_ONLY (padrão):
  POST /webhook → triagem inteligente → score do lead → corretor atribuído → lead salvo

MODO COMPLETO (USE_LLM + sem TRIAGE_ONLY):
  POST /webhook → triagem → busca de imóveis → sugestões → corretor → lead salvo

SEM IA (USE_LLM=false):
  POST /webhook → regras determinísticas → perguntas fixas → corretor → lead salvo
```
