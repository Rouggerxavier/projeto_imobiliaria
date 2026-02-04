# Lead Router - Sistema de Roteamento Automático

Sistema determinístico (sem LLM) para atribuição inteligente de leads aos corretores mais adequados.

## 🎯 Objetivo

Automatizar a distribuição de leads para corretores baseado em:
- Compatibilidade geográfica (bairros, micro-localização)
- Faixa de preço e operação (compra/aluguel)
- Especialidades (alto padrão, família, pets)
- Temperatura do lead (hot/warm/cold)
- Capacidade diária e balanceamento de carga

## 📋 Componentes

### 1. Arquivos de Dados

#### `data/agents.json`
Cadastro de corretores. Crie a partir de `agents.example.json`:

```bash
cp data/agents.example.json data/agents.json
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
- `id`: string única
- `name`: nome completo
- `whatsapp`: telefone no formato E.164
- `active`: `true` (ativo) ou `false` (inativo)
- `ops`: array com `"buy"` e/ou `"rent"`
- `coverage_neighborhoods`: lista de bairros (vazio = generalista)
- `micro_location_tags`: tags de micro-localização
- `price_min`, `price_max`: faixa de preço em R$
- `specialties`: array de especialidades
- `daily_capacity`: limite diário de leads
- `priority_tier`: `"senior"`, `"standard"` ou `"junior"`

#### `data/agent_stats.json`
Estatísticas de atribuição (gerado automaticamente):

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

- Reset diário automático
- Atualizado após cada atribuição
- Usado para balanceamento de carga

### 2. Configuração

#### Variável de Ambiente

```bash
# .env
EXPOSE_AGENT_CONTACT=false  # (padrão) não expõe WhatsApp/nome na resposta ao usuário
EXPOSE_AGENT_CONTACT=true   # expõe informações do corretor
```

**Impacto:**
- `false`: Mensagem genérica "um corretor especializado entrará em contato"
- `true`: Mensagem personalizada "o corretor Maria Santos entrará em contato"

## 🧮 Algoritmo de Pontuação

### Critérios Positivos

| Critério | Pontos | Condição |
|----------|--------|----------|
| Bairro match | +30 | Bairro do lead está em `coverage_neighborhoods` |
| Micro-localização match | +15 | Micro-loc do lead está em `micro_location_tags` |
| Faixa de preço | +20 | Budget do lead entre `price_min` e `price_max` |
| Hot + Senior | +10 | Lead quente com corretor senior |
| Warm + Standard | +5 | Lead morno com corretor padrão |
| Cold + Junior | +5 | Lead frio com corretor júnior |
| Specialty: Alto Padrão | +10 | Budget ≥ R$ 900k e specialty `"alto_padrao"` |
| Specialty: Família | +10 | Bedrooms ≥ 3 e specialty `"familia"` |
| Specialty: Pet Friendly | +5 | Pet = true e specialty `"pet_friendly"` |
| Generalista (sem bairro) | +5 | Lead sem bairro e corretor generalista |

### Penalidades

| Critério | Pontos | Condição |
|----------|--------|----------|
| Bairro incompatível | -10 | Lead tem bairro mas não está em coverage |
| Preço fora da faixa | -15 | Budget fora de `price_min`/`price_max` |
| Capacidade atingida | -100 | `assigned_today >= daily_capacity` |

### Filtros Eliminatórios (score = -1000)

- `active = false`
- Operação incompatível (ex: lead quer comprar, corretor só aluga)

### Desempate

Quando múltiplos corretores têm o mesmo score:

1. **Menor `assigned_today`** (balanceamento)
2. **Mais antigo `last_assigned_at`** (round-robin)
3. **Primeiro na lista**

### Fallback

Se nenhum corretor compatível:

1. Tenta corretores com `"generalista"` em specialties
2. Tenta qualquer corretor ativo com menor carga
3. Retorna `None` (handoff genérico)

## 🔧 Como Usar

### 1. Configurar Corretores

Edite `data/agents.json`:

```json
[
  {
    "id": "agent_joao",
    "name": "João Silva",
    "whatsapp": "+5583999992222",
    "active": true,
    "ops": ["buy", "rent"],
    "coverage_neighborhoods": ["Manaíra", "Cabo Branco"],
    "micro_location_tags": ["orla", "beira-mar", "1_quadra"],
    "price_min": 0,
    "price_max": 2000000,
    "specialties": ["familia", "investimento"],
    "daily_capacity": 25,
    "priority_tier": "senior"
  }
]
```

### 2. Testar Roteamento

```bash
# Testes unitários
python -m pytest app/tests/test_router.py -v

# Teste de integração
python test_router_integration.py
```

### 3. Usar na API

O roteamento acontece automaticamente quando a triagem é concluída (modo `TRIAGE_ONLY`).

**Request:**
```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "lead-123",
    "message": "Quero comprar em Manaíra, beira-mar, 3 quartos, até 1.5 milhão",
    "name": "Ana Silva"
  }'
```

**Response (interno, no summary):**
```json
{
  "reply": "Perfeito! Entendi o que você precisa: ...",
  "summary": {
    "assigned_agent": {
      "id": "agent_joao",
      "name": "João Silva",
      "whatsapp": "+5583999992222",
      "score": 85,
      "reasons": ["neighborhood_match_manaira", "micro_location_match_beira-mar", ...],
      "fallback": false
    },
    "routing": {
      "strategy": "score_based",
      "evaluated_agents_count": 5
    }
  }
}
```

### 4. Monitorar Atribuições

Verifique `data/agent_stats.json`:

```bash
cat data/agent_stats.json
```

Logs no console:

```
[ROUTER] assigned_agent=agent_joao name=João Silva temp=hot score=85 reasons=[...] correlation=abc123
```

## 📊 Exemplos de Configuração

### Corretor Generalista

Atende qualquer perfil quando outros não se encaixam:

```json
{
  "id": "agent_generalista",
  "name": "Corretor Backup",
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

### Corretor Especialista (Alto Padrão)

Foca em imóveis de luxo:

```json
{
  "id": "agent_luxo",
  "name": "Maria Luxury",
  "whatsapp": "+5583991111111",
  "active": true,
  "ops": ["buy"],
  "coverage_neighborhoods": ["Manaíra", "Cabo Branco"],
  "micro_location_tags": ["beira-mar"],
  "price_min": 1000000,
  "price_max": 10000000,
  "specialties": ["alto_padrao", "luxo"],
  "daily_capacity": 10,
  "priority_tier": "senior"
}
```

### Corretor para Aluguel Popular

Foco em aluguel de baixo custo:

```json
{
  "id": "agent_popular",
  "name": "Carlos Popular",
  "whatsapp": "+5583992222222",
  "active": true,
  "ops": ["rent"],
  "coverage_neighborhoods": ["Bancários", "Mangabeira", "Valentina"],
  "micro_location_tags": [">3_quadras"],
  "price_min": 0,
  "price_max": 2000,
  "specialties": ["primeira_casa", "familia"],
  "daily_capacity": 30,
  "priority_tier": "standard"
}
```

## 🧪 Testes

### Suite de Testes

```bash
# Todos os testes do router
python -m pytest app/tests/test_router.py -v

# Teste específico
python -m pytest app/tests/test_router.py::test_hot_lead_senior_agent -v

# Integração end-to-end
python test_router_integration.py
```

### Casos Cobertos

- ✅ Carga de agentes do JSON
- ✅ Lead hot → corretor senior
- ✅ Lead cold → corretor generalista/junior
- ✅ Capacidade atingida → próximo melhor
- ✅ Persistência de stats
- ✅ Arquivo ausente → fallback gracioso
- ✅ Agentes inativos → nunca selecionados
- ✅ Specialties (familia, alto_padrao, pet)
- ✅ Round-robin em empate

## 🔍 Troubleshooting

### Nenhum corretor atribuído

**Causa:** Arquivo `agents.json` vazio ou todos inativos.

**Solução:**
```bash
cp data/agents.example.json data/agents.json
# Edite e configure active=true
```

### Sempre atribui o mesmo corretor

**Causa:** Apenas um corretor ativo ou compatível.

**Solução:** Adicione mais corretores com `active=true` e coverages variadas.

### Capacidade sempre atingida

**Causa:** `daily_capacity` muito baixo ou não resetou.

**Solução:**
- Aumente `daily_capacity` em `agents.json`
- Verifique `last_reset_date` em `agent_stats.json`
- Delete `agent_stats.json` para forçar reset

### Logs não aparecem

**Logs esperados:**
```
[ROUTER] assigned_agent=... score=... reasons=[...]
[ROUTER] fallback=...
[ROUTER] no_match ...
```

**Verificar:**
- `TRIAGE_ONLY=true` no `.env`
- Triagem concluída (todos campos críticos preenchidos)
- Console do servidor

## 📚 Referências

- **Código:** `app/agent/router.py`
- **Testes:** `app/tests/test_router.py`
- **Integração:** `app/agent/controller.py` (linha ~225)
- **Documentação:** `codex.md` seção "Lead Router"

## 🚀 Próximos Passos

- [x] Dashboard de monitoramento de atribuições (JSONL em `data/routing_log.jsonl` + script `scripts/run_followups.py`)
- [ ] Webhook para notificar corretor via WhatsApp
- [ ] Histórico de performance por corretor
- [ ] Machine learning para ajuste de scores
- [ ] API REST para gerenciar corretores
