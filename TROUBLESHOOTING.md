# Troubleshooting - Guia de Solução de Problemas

## 🔴 Erro: `type=BAD_REQUEST http=400`

### Sintomas
```
ERROR: [LLM_ERROR] type=BAD_REQUEST http=400 provider=openai-compatible model=models/gemini-2.0-flash
```

### Causas Comuns

#### 1. **Formato do modelo incorreto**
❌ **ERRADO:** `models/gemini-2.0-flash`
✅ **CORRETO:** `gemini-2.5-flash` ou `gemini-1.5-flash`

**Solução:** Edite o `.env`:
```env
OPENAI_MODEL=gemini-2.5-flash
```

#### 2. **URL da API sem barra final**
❌ **ERRADO:** `https://generativelanguage.googleapis.com/v1beta/openai`
✅ **CORRETO:** `https://generativelanguage.googleapis.com/v1beta/openai/`

**Solução:** Edite o `.env`:
```env
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

#### 3. **API Key inválida ou expirada**
- A chave pode ter sido revogada
- Limite de uso foi excedido

**Solução:**
1. Acesse: https://aistudio.google.com/apikey
2. Revogue a chave antiga
3. Gere uma nova
4. Cole no `.env`

#### 4. **response_format não suportado pela Gemini**
O código já foi corrigido para detectar Gemini e usar instrução no system prompt ao invés de `response_format`.

**Confirme que está usando a versão atualizada:**
```bash
git pull  # Se estiver em um repo
# Ou verifique se app/agent/llm.py tem a detecção de Gemini
```

---

## 🟡 Erro: Chave API "morre" após 1-2 respostas

### Sintomas
- Primeiras mensagens funcionam
- Depois de 1-2 interações, começa a dar erro 400 ou 429

### Causas Prováveis

#### 1. **Rate Limit da API (limite de requisições)**
Gemini Free tem limites de:
- **15 RPM** (requests per minute)
- **1 milhão TPM** (tokens per minute)

**Solução:**
- Use **Groq** ao invés (limite maior: 30 RPM)
- Configure cooldown no código (já implementado)

#### 2. **Quota diária excedida**
A API gratuita tem limite diário de tokens.

**Solução:**
- Aguarde 24h para reset
- Ou use Groq/Ollama como alternativa

#### 3. **Timeout muito curto**
Se o timeout for muito curto, pode parecer que a API falhou.

**Solução:** Edite o `.env`:
```env
LLM_TIMEOUT=120  # 2 minutos
```

---

## 🟢 Alternativa Recomendada: Usar Groq

### Por que Groq?
- ✅ Mais estável que Gemini
- ✅ Limite maior (30 RPM)
- ✅ Respostas mais rápidas
- ✅ Gratuito

### Como Migrar para Groq

1. **Gere uma chave Groq:**
   - Acesse: https://console.groq.com/keys
   - Crie conta gratuita
   - Gere API key

2. **Edite o `.env`:**
   ```env
   # Comente as linhas do Gemini
   #OPENAI_API_KEY=sua_chave_gemini
   #OPENAI_MODEL=gemini-2.5-flash
   #OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

   # Descomente as linhas do Groq
   GROQ_API_KEY=sua_chave_groq_aqui
   GROQ_MODEL=llama-3.3-70b-versatile
   ```

3. **Reinicie o servidor:**
   ```bash
   # Ctrl+C para parar
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## 🟣 Alternativa Local: Ollama (sem limites!)

### Vantagens
- ✅ 100% local (sem API)
- ✅ Sem limites de rate
- ✅ Privacidade total
- ✅ Funciona offline

### Como Configurar

1. **Instale o Ollama:**
   - Windows/Mac/Linux: https://ollama.ai

2. **Baixe um modelo:**
   ```bash
   ollama pull llama3.2
   # Ou para melhor qualidade:
   ollama pull llama3.1:8b
   ```

3. **Configure o `.env`:**
   ```env
   OPENAI_API_KEY=ollama
   OPENAI_MODEL=llama3.2
   OPENAI_BASE_URL=http://localhost:11434/v1
   LLM_TIMEOUT=120
   ```

4. **Inicie o Ollama (se não iniciou automaticamente):**
   ```bash
   ollama serve
   ```

---

## 🔍 Debug: Como Verificar se o LLM Está Funcionando

### 1. Teste de Conexão
```python
# Rode no terminal Python
python -c "from app.agent.llm import test_llm_connection; test_llm_connection()"
```

**Resposta esperada:**
```
[OK] Conexão com gemini OK: {'status': 'OK'}
```

### 2. Verifique os Logs
Ao rodar o servidor, procure por:
```
[LLM] Usando Google Gemini com modelo gemini-2.5-flash
```

Se ver `[LLM] Nenhuma API key configurada`, revise o `.env`.

### 3. Teste Manual via cURL
```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-123",
    "message": "oi",
    "name": "Teste"
  }'
```

**Resposta esperada:** JSON com uma mensagem do agente.

---

## 📋 Checklist de Verificação

Antes de reportar um problema, confirme:

- [ ] Arquivo `.env` existe e está configurado
- [ ] API key está preenchida (não é `sua_chave_aqui`)
- [ ] Modelo está no formato correto (sem `models/`)
- [ ] URL da API tem barra final `/`
- [ ] Servidor está rodando (`python -m uvicorn app.main:app --reload`)
- [ ] Porta 8000 não está sendo usada por outro processo
- [ ] `.venv` está ativado (`which python` deve mostrar o venv)

---

## 🆘 Ainda com Problemas?

### 1. Ative logs detalhados
```env
LOG_LEVEL=debug
```

### 2. Teste com fallback (sem LLM)
```env
USE_LLM=false
```

Se funcionar com `USE_LLM=false`, o problema está na configuração do LLM.

### 3. Verifique a versão do Python
```bash
python --version  # Deve ser 3.8+
```

### 4. Reinstale dependências
```bash
pip install --upgrade -r requirements.txt
```

---

## 📖 Logs de Erro Comuns

### `[LLM_ERROR] type=AUTH_INVALID_KEY`
- **Causa:** API key inválida
- **Solução:** Gere nova chave e atualize o `.env`

### `[LLM_ERROR] type=RATE_LIMIT_RPM`
- **Causa:** Excedeu limite de requisições por minuto
- **Solução:** Aguarde 60s ou use Groq

### `[LLM_ERROR] type=QUOTA_EXHAUSTED_DAILY`
- **Causa:** Limite diário excedido
- **Solução:** Aguarde 24h ou mude para Groq/Ollama

### `[LLM_ERROR] type=MODEL_NOT_FOUND`
- **Causa:** Nome do modelo incorreto
- **Solução:** Corrija `OPENAI_MODEL` para `gemini-2.5-flash`

### `[LLM_ERROR] type=NETWORK_TIMEOUT`
- **Causa:** Resposta demorou demais
- **Solução:** Aumente `LLM_TIMEOUT=180`
