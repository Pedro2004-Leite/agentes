# Heartbeat — Verificacoes Periodicas

## Agendamentos (via cron do OpenClaw)

### Manha — 08:00 dias uteis (Seg-Sex)
```
python scripts/market_briefing.py
```
- Briefing matinal completo (indices EUA + Europa + FX + watchlist)
- Se output mostrar VIX > 25 ou eventos de risco: alerta imediato

### Segunda-feira — 08:15
- Verificar earnings reports da semana para a watchlist
- Verificar calendario economico: FOMC, CPI, NFP, decisoes de bancos centrais
- Atualizar niveis tecnicos da watchlist (suportes/resistencias relevantes)

### Todos os dias — 22:00
```
python scripts/portfolio_tracker.py
```
- Verificar P&L das posicoes abertas
- Alertar se algum stop loss foi atingido
- Alertar se algum take profit foi atingido ou esta proximo
- Rever se as posicoes ainda fazem sentido (mudanca de tendencia?)

### Sexta-feira — 18:00 (fecho semanal)
- Performance semanal da watchlist
- Screener de setups para a semana seguinte:
  ```
  python scripts/screener.py --rsi-oversold --universe sp500 --top 20
  python scripts/screener.py --bollinger-squeeze --above-sma200 --top 20
  ```
- Resumo semanal: melhores/piores performers, P&L do portfolio
- Preparar watchlist para segunda-feira

## Checklist manual do trader (coisas que o agente nao faz sozinho)
- [ ] Rever posicoes abertas — stops continuam validos?
- [ ] Verificar earnings na proxima semana para posicoes abertas
- [ ] Atualizar watchlist conforme setups identificados
- [ ] Rever risk management — alguma posicao > 20% do portfolio?
- [ ] Journal de trading — anotar raciocinio de cada entrada/saida
