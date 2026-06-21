# Agentes Diários

Sistema de agentes AI. Cada agente vive na sua própria pasta com ficheiros markdown que definem personalidade, regras, ferramentas e preferências.

## Bootstrap automático (primeira execução após clone)

**AO INICIAR CONVERSA NESTE REPO, VERIFICA E EXECUTA O SEGUINTE:**

1. **Verificar Python:** corre `python --version`. Se falhar, tenta `python3 --version` ou `py --version`. Se não houver Python, instrui o utilizador a instalar do `python.org` ou `winget install python`.

2. **Instalar dependências:**
   ```bash
   cd analista-financeiro/scripts
   pip install -r requirements.txt
   ```
   Se `pip` falhar, tenta `python -m pip install -r requirements.txt`.

3. **Verificar que tudo compila:**
   ```bash
   python -c "
   import py_compile
   scripts = ['config.py','market_briefing.py','stock_analysis.py','screener.py','value_screener.py','portfolio_tracker.py','patterns.py','pre_trade_check.py']
   for s in scripts: py_compile.compile(s, doraise=True); print(f'  {s} OK')
   print('Todos os scripts prontos.')
   "
   ```

4. **Criar TOOLS.md local se não existir:**
   ```bash
   # Windows
   if not exist ..\TOOLS.md copy ..\TOOLS.md.example ..\TOOLS.md
   # Unix
   test -f ../TOOLS.md || cp ../TOOLS.md.example ../TOOLS.md
   ```

5. **Smoke test — briefing matinal:**
   ```bash
   python market_briefing.py
   ```
   Se correr sem erros e gerar `reports/YYYY-MM-DD/briefing.md`, está tudo operacional.

6. **Resumo final:** diz ao utilizador quantos scripts estão prontos e sugere o primeiro comando:
   ```
   python stock_analysis.py AAPL
   ```

**Após bootstrap, o agente está vivo.** O utilizador pode pedir qualquer coisa da secção "Comandos" abaixo.

---

## Estrutura do projeto

```
agentes/
├── _template/              ← Molde para criar novos agentes
├── analista-financeiro/    ← Agente de análise financeira (7 scripts Python)
├── setup.ps1               ← Script pós-clone
├── novo-agente.ps1         ← Cria novo agente a partir do _template
├── CLAUDE.md               ← Este ficheiro
└── README.md               ← Documentação completa
```

## Ficheiros de cada agente

| Ficheiro | Função |
|----------|--------|
| `SOUL.md` | Personalidade, tom, identidade do agente |
| `AGENTS.md` | Regras de comportamento, ferramentas permitidas, workflow, comandos |
| `USER.md` | Preferências do utilizador (objetivos, hábitos, ferramentas) |
| `IDENTITY.md` | Nome, emoji, vibe, avatar do agente |
| `TOOLS.md.example` | Template de config local — copiar para `TOOLS.md` |
| `HEARTBEAT.md` | Tarefas agendadas periódicas (cron jobs) |

`TOOLS.md` e `positions.json` estão no `.gitignore` — cada máquina tem os seus.

---

## 🍺 Carlsberg (`analista-financeiro/`)

### Setup rápido
```bash
cd analista-financeiro/scripts
pip install -r requirements.txt
python market_briefing.py          # testar
```

### Scripts (8)

| Script | Comando exemplo | Função |
|--------|----------------|--------|
| `market_briefing.py` | `python market_briefing.py` | Briefing matinal: futures, yield curve, sector rotation, indices EUA+Europa, watchlist com níveis |
| `stock_analysis.py` | `python stock_analysis.py AAPL` | Relatório institucional 8 secções: DCF 3 cenários, quarterly trends, earnings beat rate, insider trading, technical |
| `screener.py` | `python screener.py --rsi-oversold --volume-spike` | 14 filtros técnicos, paralelo (12 workers), S&P 500 / NASDAQ 100 / Euro Stoxx 50 |
| `value_screener.py` | `python value_screener.py --deep-value` | Screening fundamentalista: P/E, P/B, ROE, margens, crescimento, D/E. 5 presets (Deep Value, Quality, Growth, Dividend, GARP) |
| `portfolio_tracker.py` | `python portfolio_tracker.py --risk` | Tracking posições, matriz correlação, beta, profit factor, expectancy, position sizing |
| `patterns.py` | `python patterns.py AAPL` | 9 padrões candlestick: hammer, engulfing, doji, morning/evening star, gaps |
| `pre_trade_check.py` | `python pre_trade_check.py AAPL 150 140 --target 170` | Checklist 6 validações pré-trade (R/R, sizing, earnings, correlação, setor, técnico) |
| `config.py` | (importado pelos outros) | Watchlist 19 tickers, 11 índices, 4 yields, 4 futures, 12 sector ETFs |

### Comandos rápidos

```bash
# Mercado
python market_briefing.py                                           # Briefing completo
python screener.py --rsi-oversold --volume-spike                    # Bounces com volume
python screener.py --bollinger-squeeze --above-sma200               # Breakouts iminentes
python screener.py --short-squeeze                                  # Short squeeze candidates

# Value / Fundamental
python value_screener.py --deep-value                               # Graham-style: P/E<15, P/B<1.5
python value_screener.py --quality                                  # ROE alto, margens altas, baixa divida
python value_screener.py --growth                                   # Crescimento acelerado, PEG baixo
python value_screener.py --dividend-value                           # Yield >2%, payout seguro, P/E razoavel
python value_screener.py --pe-under 15 --roe-over 20 --de-under 0.5  # Combinacao custom

# Análise
python stock_analysis.py NVDA                                       # Análise completa
python stock_analysis.py NVDA --compare AMD,AVGO                    # + peer comparison
python patterns.py AAPL --days 5                                    # Padrões candlestick

# Trading
python pre_trade_check.py AAPL 150.00 140.00 --target 170.00       # Validar entrada
python portfolio_tracker.py --add AAPL 10 150.00 --stop 140.00 --target 170.00
python portfolio_tracker.py                                         # Ver portfolio
python portfolio_tracker.py --risk                                  # Análise de risco
python portfolio_tracker.py --size AAPL 150 140                     # Position sizing
```

### Dependências
```
yfinance pandas numpy tabulate requests-cache fredapi
```

### Perfil do utilizador
- Portugal (WET/BST), swing trading, ~5k EUR, foco em autonomia financeira
- Preferência: dados > opiniões, respostas curtas, níveis claros (entry/stop/target)
- Regras: max 2% risco por trade, R/R mínimo 2:1, max 5 posições simultâneas
- Watchlist: AAPL, MSFT, NVDA, AMD, AVGO, JPM, V, MA, PYPL, AMZN, TSLA, RACE, LVMUY, XOM, GLEN.L, RTX, LMT, ABBV, JNJ

---

## OpenClaw

O OpenClaw está em `C:\Creative\openclaw\`. A config local (`openclaw.local.json`) aponta para os workspaces dos agentes.

```json
{
  "agents": {
    "defaults": {
      "workspace": "C:/Creative/agents/analista-financeiro"
    }
  }
}
```

Para adicionar o analista-financeiro, criar uma entry no array `agents` com o workspace correspondente.

## Criar novo agente

```powershell
.\novo-agente.ps1 <slug> "Nome Bonito"
```

Depois editar os ficheiros na nova pasta.

## Convenções

- Tudo em Português de Portugal
- Respostas curtas e diretas
- Foco no que é acionável, sem ruído
- NUNCA comitar `TOOLS.md`, `positions.json`, `reports/` ou `.yfinance_cache/`
