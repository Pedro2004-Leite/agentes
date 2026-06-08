# Agentes Diários

Cada agente vive na sua própria pasta com os seguintes ficheiros:

| Ficheiro | O que define |
|----------|-------------|
| `SOUL.md` | Personalidade, tom, identidade do agente |
| `AGENTS.md` | Regras de comportamento, ferramentas permitidas, limites |
| `USER.md` | Preferências do utilizador |
| `IDENTITY.md` | Nome, emoji, vibe, avatar do agente |
| `TOOLS.md.example` | Template de configuração local — copia para `TOOLS.md` |
| `HEARTBEAT.md` | Tarefas agendadas periódicas |

> **Nota:** `TOOLS.md` é gitignored. Cada máquina tem o seu. Copia do `.example`.

## Clone e primeiro uso

```powershell
git clone <url-do-repo> agentes
cd agentes
.\setup.ps1
```

O `setup.ps1` mostra o estado dos agentes e os próximos passos.

Depois de clonar, para cada agente:
1. Copia `TOOLS.md.example` → `TOOLS.md` e preenche com os paths/creds da máquina
2. Se for o `analista-financeiro`: `pip install -r scripts/requirements.txt`

## Criar um novo agente

```powershell
.\novo-agente.ps1 <slug> "Nome Bonito"
```

Depois edita os ficheiros gerados e aponta o OpenClaw para a nova pasta.

## Agentes ativos

| Agente | Pasta | Descrição |
|--------|-------|-----------|
| 📋 Organizador Diário | `organizador-diario/` | Produtividade pessoal, priorização, hábitos |
| 📈 Analista Financeiro | `analista-financeiro/` | Briefing matinal, stock analysis, screening |

### Analista Financeiro — Uso rápido

```bash
# Briefing matinal (indices, noticias, watchlist)
python scripts/market_briefing.py

# Analise completa de uma stock (estilo relatorio profissional)
python scripts/stock_analysis.py AAPL
python scripts/stock_analysis.py AAPL --compare MSFT,GOOGL

# Screening tecnico
python scripts/screener.py --rsi-oversold
python scripts/screener.py --macd-bullish --volume-spike
python scripts/screener.py --universe "AAPL,MSFT,NVDA,TSLA" --rsi-oversold
```

Requerimentos: `pip install yfinance pandas numpy tabulate`

## Próximos agentes sugeridos

- [ ] `revisor-de-habitos` — acompanha hábitos diários e sugere ajustes
- [ ] `planeador-semanal` — planeia a semana ao domingo à noite
- [ ] `foco-profundo` — ajuda a entrar em sessões de deep work
- [ ] `gestor-de-email` — triagem inteligente de email
- [ ] `saude-e-energia` — lembra de pausas, água, alongamentos
- [ ] `aprendizagem` — organiza tópicos de estudo e revisão espaçada
- [ ] `reflexao-semanal` — retrospectiva de sábado de manhã
