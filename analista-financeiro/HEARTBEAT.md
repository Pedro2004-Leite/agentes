# Heartbeat — Verificacoes Periodicas

## Agendamentos (via cron do OpenClaw)

### Manha — 08:00 dias uteis (Seg-Sex)
```
python scripts/market_briefing.py
```
- Briefing matinal completo (futures pre-market + indices + yield curve + sector rotation + FX + watchlist com niveis chave)
- Se output mostrar VIX > 25 ou 2Y-10Y invertido: alerta imediato

### Segunda-feira — 08:15
- Verificar earnings reports da semana para a watchlist
- Verificar calendario economico: FOMC, CPI, NFP, decisoes de bancos centrais
- Screener de short squeeze: `python scripts/screener.py --short-squeeze --universe sp500`
- Atualizar niveis tecnicos da watchlist (suportes/resistencias relevantes)

### Todos os dias — 22:00
```
python scripts/portfolio_tracker.py
python scripts/portfolio_tracker.py --risk
```
- Verificar P&L das posicoes abertas
- Matriz de correlacao — novas concentracoes de risco?
- Alertar se algum stop loss foi atingido
- Alertar se algum take profit foi atingido ou esta proximo

### Sexta-feira — 18:00 (fecho semanal)
- Performance semanal da watchlist
- Screener de setups para a semana seguinte:
  ```
  python scripts/screener.py --rsi-oversold --universe sp500 --top 20
  python scripts/screener.py --bollinger-squeeze --above-sma200 --top 20
  ```
- Resumo semanal: melhores/piores performers, P&L do portfolio
- `python scripts/portfolio_tracker.py --risk` — profit factor e expectancy atualizados
- Preparar watchlist para segunda-feira

## Checklist manual do trader
- [ ] Rever posicoes abertas — stops continuam validos?
- [ ] `python scripts/pre_trade_check.py <TICKER> <ENTRY> <STOP>` antes de cada entrada nova
- [ ] Verificar earnings na proxima semana para posicoes abertas
- [ ] Atualizar watchlist conforme setups identificados
- [ ] Rever risk management — alguma posicao > 20% do portfolio?
- [ ] Journal de trading — anotar raciocinio de cada entrada/saida
