# Carlsberg — Guia de Setup Autónomo (PC Destino)

Seguir estes passos **no PC onde o Carlsberg vai viver 24/7**.

## Pré-requisitos

Ter à mão:
- **Bot token** do Telegram (criar com [@BotFather](https://t.me/BotFather))
- **User ID** numérico do Telegram (descobrir com [@userinfobot](https://t.me/userinfobot))

## 1. Clonar repo

```bash
git clone https://github.com/pleite/Creative-agents.git C:\Creative\agents
```

Ou fazer `git pull` se já existir.

## 2. Instalar dependências Python

```bash
cd C:\Creative\agents\analista-financeiro\scripts
pip install -r requirements.txt
```

## 3. Criar TOOLS.md local

```bash
cd C:\Creative\agents\analista-financeiro
copy TOOLS.md.example TOOLS.md
```

Preencher no ficheiro:
- Python path: `python`
- OS: Windows 11 (ou o que for)
- Tudo o resto pode ficar default.

## 4. Instalar e configurar OpenClaw

O OpenClaw está em https://github.com/openclaw/openclaw — clonar e instalar conforme a doc.

## 5. Configurar openclaw.json

Criar/editar `C:\Users\<USER>\.openclaw\openclaw.json`:

```json
{
  "agents": {
    "defaults": {
      "workspace": "C:\\Creative\\agents\\analista-financeiro",
      "model": "deepseek/deepseek-v4-flash",
      "userTimezone": "Europe/Lisbon"
    }
  },
  "models": {
    "providers": {
      "deepseek": {
        "api": "openai-completions",
        "baseUrl": "https://api.deepseek.com"
      }
    }
  },
  "channels": {
    "telegram": {
      "botToken": "<BOT_TOKEN_AQUI>",
      "dmPolicy": "allowlist",
      "allowFrom": ["<USER_ID_AQUI>"],
      "groups": {}
    }
  },
  "gateway": {
    "mode": "local",
    "port": 18789,
    "bind": "loopback"
  }
}
```

**IMPORTANTE:** Substituir `<BOT_TOKEN_AQUI>` e `<USER_ID_AQUI>` pelos valores reais.
NUNCA comitar o token — este ficheiro é local.

## 6. Validar config

```bash
openclaw config validate
```

Corrigir warnings antes de prosseguir.

## 7. Instalar daemon Windows

```bash
openclaw gateway install
openclaw gateway start
openclaw gateway status
```

O `gateway install` cria uma scheduled task que arranca com o login do Windows.

## 8. Criar cron jobs

### 8.1 Briefing Matinal — Seg-Sex 08:00

```bash
openclaw cron add \
  --name "Briefing Matinal" \
  --schedule "0 8 * * 1-5" \
  --timezone "Europe/Lisbon" \
  --session isolated \
  --announce \
  --channel telegram \
  --to <USER_ID> \
  --prompt "Executa python scripts/market_briefing.py. Lê o briefing gerado e envia um resumo curto com: direção dos futures, VIX, yield curve, rotação setorial, e alertas da watchlist. Sê direto e acionável."
```

### 8.2 Checklist Segunda-feira — Seg 08:15

```bash
openclaw cron add \
  --name "Checklist Segunda" \
  --schedule "15 8 * * 1" \
  --timezone "Europe/Lisbon" \
  --session isolated \
  --announce \
  --channel telegram \
  --to <USER_ID> \
  --tools exec,read,web_search \
  --prompt "É segunda-feira de manhã. Faz: (1) pesquisa earnings reports desta semana para a watchlist (AAPL, MSFT, NVDA, AMD, AVGO, JPM, V, MA, PYPL, AMZN, TSLA, RACE, LVMUY, XOM, GLEN.L, RTX, LMT, ABBV, JNJ). (2) pesquisa calendário económico: FOMC, CPI, NFP, decisões de bancos centrais. (3) executa python scripts/screener.py --short-squeeze --universe sp500. (4) Resume tudo de forma acionável."
```

### 8.3 Verificação Portfolio — Diário 22:00

```bash
openclaw cron add \
  --name "Verificacao Portfolio" \
  --schedule "0 22 * * *" \
  --timezone "Europe/Lisbon" \
  --session isolated \
  --announce \
  --channel telegram \
  --to <USER_ID> \
  --tools exec,read \
  --prompt "Executa python scripts/portfolio_tracker.py e depois python scripts/portfolio_tracker.py --risk. Lê os outputs e resume: P&L atual, stops atingidos, targets próximos, correlações perigosas, profit factor. Se algo crítico (stop atingido, correlação >0.8), alerta imediato no início da mensagem."
```

### 8.4 Resumo Semanal — Sexta 18:00

```bash
openclaw cron add \
  --name "Resumo Semanal" \
  --schedule "0 18 * * 5" \
  --timezone "Europe/Lisbon" \
  --session isolated \
  --announce \
  --channel telegram \
  --to <USER_ID> \
  --tools exec,read \
  --prompt "É sexta-feira ao fim do dia. Faz: (1) executa python scripts/screener.py --rsi-oversold --universe sp500 --top 20. (2) executa python scripts/screener.py --bollinger-squeeze --above-sma200 --top 20. (3) executa python scripts/portfolio_tracker.py --risk. (4) Resume: melhores/piores da semana, setups para segunda, P&L semanal, profit factor e expectancy. Prepara watchlist para a semana seguinte."
```

**IMPORTANTE:** Substituir `<USER_ID>` pelo ID numérico do Telegram em todos os comandos acima.

## 9. Verificar tudo

### 9.1 Ping via Telegram

Abrir o Telegram, enviar `ping` para o bot. Deve responder `pong`.

### 9.2 Testar um cron job manualmente

```bash
openclaw cron list                # Ver IDs dos jobs
openclaw cron run <JOB_ID>        # Executa agora para testar
```

### 9.3 Testar comandos on-demand via Telegram

Enviar para o bot:
- `analise NVDA` — deve correr stock_analysis.py e responder com resumo
- `briefing` — deve correr market_briefing.py
- `portfolio` — deve correr portfolio_tracker.py

## 10. Configurar o bot no Telegram

No [@BotFather](https://t.me/BotFather):
- `/setdescription` — descrever o bot
- `/setabouttext` — texto curto
- `/setuserpic` — avatar (opcional)
- `/setcommands` — lista de comandos sugeridos:
  ```
  briefing - Briefing matinal
  analise <ticker> - Análise completa de uma ação
  screener - Screener técnico
  portfolio - Ver portfolio
  risco - Análise de risco
  precheck - Checklist pré-trade
  ajuda - Comandos disponíveis
  ```

## Ficheiros gitignored (cada PC tem os seus)

- `TOOLS.md` — config local de paths e API keys
- `positions.json` — tracking de posições
- `reports/` — relatórios gerados
- `.yfinance_cache/` — cache de dados

---

Setup completo → Carlsberg está vivo e a responder no Telegram.
