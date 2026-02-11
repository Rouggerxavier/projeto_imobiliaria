# 🚀 Guia Rápido de Deploy - WhatsApp Cloud API

## ✅ Checklist Pré-Deploy

Antes de configurar o WhatsApp, certifique-se que:

- [x] Código implementado e testado
- [x] Serviço no Render está "Live"
- [ ] Variáveis de ambiente configuradas no Render
- [ ] Webhook configurado no Meta Developers
- [ ] Credenciais do WhatsApp Cloud API obtidas

---

## 📋 Passo 1: Configurar Variáveis de Ambiente no Render

1. Acesse: https://dashboard.render.com
2. Selecione seu serviço
3. Vá em **Environment** (menu lateral)
4. Adicione as variáveis abaixo:

### Obrigatórias

```bash
# Token para verificação do webhook (gere um aleatório seguro)
WHATSAPP_VERIFY_TOKEN=<gere_um_token_aleatorio>
```

**Como gerar token seguro:**
```bash
# No terminal (Git Bash, WSL ou Linux):
openssl rand -hex 32

# Ou use um gerador online:
# https://www.random.org/strings/?num=1&len=32&digits=on&upperalpha=on&loweralpha=on
```

### Recomendadas para Produção

```bash
# App Secret para validação de assinatura (X-Hub-Signature-256)
WHATSAPP_APP_SECRET=<seu_app_secret_do_meta>

# Environment
APP_ENV=production
LOG_LEVEL=INFO
```

### Modo Teste (sem enviar mensagens)

```bash
# Permite receber webhooks sem processar/enviar mensagens
DISABLE_WHATSAPP_SEND=true
```

### Para Envio de Mensagens (quando configurar)

```bash
WHATSAPP_ACCESS_TOKEN=<seu_access_token>
WHATSAPP_PHONE_NUMBER_ID=<seu_phone_number_id>
```

4. Clique em **Save Changes**
5. Aguarde o serviço reiniciar (~ 1-2 min)

---

## 📱 Passo 2: Obter Credenciais do WhatsApp Cloud API

### 2.1. Criar/Configurar App no Meta

1. Acesse: https://developers.facebook.com/apps/
2. Crie um novo app ou use existente
3. Adicione o produto **WhatsApp**

### 2.2. Obter APP_SECRET

1. No Dashboard do App → **Settings** → **Basic**
2. Copie o **App Secret**
3. Adicione no Render como `WHATSAPP_APP_SECRET`

### 2.3. Obter ACCESS_TOKEN e PHONE_NUMBER_ID

1. WhatsApp → **Getting Started**
2. **Temporary access token**: copie e use (válido 24h)
   - Para produção, gere um **System User Token** permanente
3. **Phone Number ID**: copie o número de teste ou configure seu número

---

## 🔗 Passo 3: Configurar Webhook no Meta

1. No Meta App → **WhatsApp** → **Configuration**
2. Clique em **Edit** na seção Webhook
3. Preencha:

   ```
   Callback URL: https://seu-app.onrender.com/webhook/whatsapp
   Verify Token: <o_mesmo_valor_de_WHATSAPP_VERIFY_TOKEN>
   ```

4. Clique em **Verify and Save**
   - ✅ Se aparecer mensagem de sucesso, o webhook está configurado!
   - ❌ Se der erro 403/500, verifique:
     - `WHATSAPP_VERIFY_TOKEN` está correto no Render?
     - A URL está acessível? Teste: `https://seu-app.onrender.com/health`
     - O serviço reiniciou após adicionar as variáveis?

5. **Subscribe to webhooks**: marque os eventos desejados
   - `messages` (obrigatório)
   - `message_status` (opcional - status de entrega)
   - Outros conforme necessidade

6. Clique em **Save**

---

## 🧪 Passo 4: Testar a Integração

### 4.1. Testar Health Check

```bash
curl https://seu-app.onrender.com/health
```

**Resposta esperada:**
```json
{"status":"ok","timestamp":"2025-02-11T12:30:45.123456"}
```

### 4.2. Testar Verificação do Webhook (GET)

```bash
curl "https://seu-app.onrender.com/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=SEU_TOKEN_AQUI&hub.challenge=test123"
```

**Resposta esperada:**
```
test123
```

Se retornar 403:
- Verifique se `WHATSAPP_VERIFY_TOKEN` está correto
- Confira os logs no Render

### 4.3. Testar Recebimento de Evento (POST)

```bash
curl -X POST https://seu-app.onrender.com/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "id": "123456",
      "changes": [{
        "value": {
          "messages": [{
            "from": "5511999999999",
            "text": {"body": "teste"}
          }]
        }
      }]
    }]
  }'
```

**Resposta esperada:**
```json
{"ok":true}
```

### 4.4. Verificar Logs no Render

1. Dashboard → seu serviço → **Logs**
2. Procure por:
   ```
   WhatsApp webhook received - type=whatsapp_business_account, entries=1, messages=1
   ```

---

## 🔒 Segurança e Boas Práticas

### ✅ Implementado

- ✅ Validação de assinatura X-Hub-Signature-256 (quando `WHATSAPP_APP_SECRET` configurado)
- ✅ Sanitização automática de tokens/secrets nos logs
- ✅ Modo teste com `DISABLE_WHATSAPP_SEND=true`
- ✅ Validação de configuração no startup
- ✅ Resposta rápida (200 OK) para evitar timeouts
- ✅ HTTPS habilitado automaticamente pelo Render

### 🔐 Recomendações

1. **Sempre configure** `WHATSAPP_APP_SECRET` em produção
2. Use tokens fortes (32+ caracteres aleatórios)
3. **Não compartilhe** tokens em código ou repositórios
4. Monitore logs para tentativas de acesso não autorizado
5. Configure rate limiting se receber muitas mensagens

---

## 🐛 Troubleshooting

### Erro: "WHATSAPP_VERIFY_TOKEN not configured"

**Causa:** Variável de ambiente não definida ou serviço não reiniciou.

**Solução:**
1. Vá em Render → Environment
2. Adicione `WHATSAPP_VERIFY_TOKEN`
3. Aguarde reinício automático (ou force: Manual Deploy → Clear build cache & deploy)

### Erro: "Invalid signature" (403 no POST)

**Causa:** Assinatura X-Hub-Signature-256 inválida.

**Solução:**
- Se em desenvolvimento, deixe `WHATSAPP_APP_SECRET` vazio (permite testes)
- Se em produção, verifique se `WHATSAPP_APP_SECRET` está correto
- Verifique logs para detalhes

### Webhook não recebe eventos

**Possíveis causas:**
1. Eventos não marcados no Meta: Webhook → Subscribe to events
2. Número de teste não autorizado: adicione número de teste no Meta
3. Serviço offline: verifique status no Render
4. Firewall/bloqueio: Render não tem restrições, mas verifique logs

### Logs mostram "API key expired" (Gemini)

**Causa:** API key do Gemini expirada (não afeta webhook).

**Solução:**
- Sistema usa **fallback determinístico** quando LLM falha
- Para usar LLM: renove a key em https://aistudio.google.com/apikey
- Configure no Render: `OPENAI_API_KEY=nova_key`

---

## 📊 Monitoramento

### Logs Importantes

Verifique regularmente no Render → Logs:

```bash
# Configuração no startup
Configuration warning: WHATSAPP_APP_SECRET not set - signature validation disabled

# Webhook recebido
WhatsApp webhook received - type=whatsapp_business_account, entries=1, messages=1

# Verificação bem-sucedida
Webhook verification successful - returning challenge

# Erro de validação
Invalid webhook signature - rejecting request from 123.45.67.89
```

### Métricas Recomendadas

Monitore (manualmente ou com ferramentas):
- Taxa de sucesso do webhook (200 OK)
- Taxa de rejeição (403 Forbidden)
- Latência de resposta (< 5s recomendado)
- Volume de mensagens recebidas

---

## ✅ Próximos Passos

Após webhook configurado e testado:

1. [ ] Implementar processamento de mensagens WhatsApp
   - Conectar com `handle_message()` do agente
   - Extrair `from`, `text.body` do payload
   - Mapear `session_id` para número do WhatsApp

2. [ ] Implementar envio de mensagens
   - Usar WhatsApp Cloud API: `POST /messages`
   - Gerenciar tokens e rate limits
   - Tratar erros de envio

3. [ ] Configurar System User Token (produção)
   - Token temporário expira em 24h
   - Gere token permanente no Meta Business Manager

4. [ ] Escalar para produção
   - Redis para sessões (múltiplas instâncias)
   - Queue para processamento assíncrono
   - Métricas e alertas

---

## 📚 Recursos

- **WhatsApp Cloud API Docs**: https://developers.facebook.com/docs/whatsapp/cloud-api
- **Meta App Dashboard**: https://developers.facebook.com/apps/
- **Render Docs**: https://docs.render.com/
- **Código do Projeto**: `/app/routes/whatsapp.py`

---

**🎉 Parabéns!** Seu webhook WhatsApp está pronto para produção.

Para dúvidas ou problemas, verifique os logs no Render ou consulte a documentação oficial do WhatsApp Cloud API.
