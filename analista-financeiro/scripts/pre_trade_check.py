"""
Checklist pre-trade — valida se um trade faz sentido antes de entrar.
Uso: python pre_trade_check.py <TICKER> <ENTRY> <STOP> [--target TARGET]

Exemplo:
  python pre_trade_check.py AAPL 180.00 175.00 --target 195.00
  python pre_trade_check.py NVDA 145.00 138.00
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

# Fix Unicode emoji crash on Windows cp1252 terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import (
    POSITIONS_FILE, MAX_RISK_PER_TRADE_PCT, MIN_RISK_REWARD_RATIO,
    WATCHLIST,
)

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    import requests_cache
    requests_cache.install_cache(
        str(Path(__file__).parent / '.yfinance_cache'),
        expire_after=900,
        allowable_methods=['GET'],
    )
except ImportError:
    print("Erro: instala as dependencias")
    print("  pip install yfinance pandas numpy requests-cache")
    sys.exit(1)


def fmt_pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"{val*100:.1f}%" if abs(val) < 10 else f"{val*100:.2f}%"


def load_positions():
    if POSITIONS_FILE.exists():
        with open(POSITIONS_FILE, "r") as f:
            return json.load(f)
    return []


def check_earnings_proximity(ticker):
    """Verifica se ha earnings nos proximos 7 dias."""
    try:
        t = yf.Ticker(ticker)
        earnings_date = t.info.get("earningsTimestamp")
        earnings_start = t.info.get("earningsTimestampStart")
        for ed in [earnings_date, earnings_start]:
            if ed:
                dt = datetime.fromtimestamp(ed)
                if abs((dt - datetime.now()).days) <= 7:
                    return True, dt.strftime("%d/%m/%Y")
        return False, None
    except Exception:
        return False, None


def check_correlation(ticker, open_positions):
    """Calcula correlacao com posicoes abertas."""
    if not open_positions:
        return []

    results = []
    open_tickers = [p["ticker"] for p in open_positions if p["status"] == "open"]

    if not open_tickers:
        return []

    # Fetch returns for ticker + positions
    all_tickers = [ticker] + open_tickers
    closes = {}
    for tkr in all_tickers:
        try:
            t = yf.Ticker(tkr)
            hist = t.history(period="3mo")
            if not hist.empty:
                closes[tkr] = hist["Close"].pct_change().dropna()
        except Exception:
            pass

    if ticker not in closes:
        return []

    for ot in open_tickers:
        if ot in closes and ticker in closes:
            common_idx = closes[ticker].index.intersection(closes[ot].index)
            if len(common_idx) > 10:
                corr = closes[ticker][common_idx].corr(closes[ot][common_idx])
                results.append((ot, corr, "HIGH" if corr > 0.7 else "MEDIUM" if corr > 0.4 else "LOW"))

    return results


def check_sector_concentration(ticker, open_positions):
    """Verifica concentracao setorial."""
    try:
        t = yf.Ticker(ticker)
        ticker_sector = t.info.get("sector", "Unknown")
    except Exception:
        ticker_sector = "Unknown"

    sectors = {ticker_sector: 1}
    for p in open_positions:
        if p["status"] != "open":
            continue
        try:
            t = yf.Ticker(p["ticker"])
            sec = t.info.get("sector", "Unknown")
            sectors[sec] = sectors.get(sec, 0) + 1
        except Exception:
            pass

    count = sectors.get(ticker_sector, 0)
    total = sum(sectors.values())
    concentration = count / total if total > 0 else 0

    return ticker_sector, count, total, concentration


def run_checklist(ticker, entry, stop, target=None, capital=5000):
    """Executa checklist completa e retorna resultados."""
    print(f"\n{'='*60}")
    print(f"  CHECKLIST PRE-TRADE: {ticker.upper()}")
    print(f"  Entrada: ${entry:.2f} | Stop: ${stop:.2f}", end="")
    if target:
        print(f" | Target: ${target:.2f}")
    else:
        print()
    print(f"{'='*60}\n")

    results = []
    green = 0
    yellow = 0
    red = 0

    # ---- 1. Risk/Reward ----
    risk = entry - stop
    if target:
        reward = target - entry
        rr = reward / risk if risk > 0 else 0
    else:
        rr = None

    print("1. RISK/REWARD")
    if risk <= 0:
        print(f"   🔴 Stop (${stop:.2f}) deve estar ABAIXO da entrada (${entry:.2f})!")
        red += 1
        results.append(("R/R Ratio", "RED", f"Stop acima da entrada"))
    elif rr and rr >= MIN_RISK_REWARD_RATIO:
        print(f"   🟢 R/R = 1:{rr:.1f} — acima do minimo (1:{MIN_RISK_REWARD_RATIO:.0f})")
        green += 1
        results.append(("R/R Ratio", "GREEN", f"1:{rr:.1f}"))
    elif rr:
        print(f"   🟡 R/R = 1:{rr:.1f} — abaixo do minimo (1:{MIN_RISK_REWARD_RATIO:.0f})")
        yellow += 1
        results.append(("R/R Ratio", "YELLOW", f"1:{rr:.1f} < min {MIN_RISK_REWARD_RATIO}"))
    else:
        print(f"   ⚪ R/R = N/D — define um target para calcular")
        results.append(("R/R Ratio", "NEUTRAL", "Sem target definido"))
    print()

    # ---- 2. Position Sizing ----
    print("2. POSITION SIZING (regra dos 2%)")
    max_risk_amount = capital * (MAX_RISK_PER_TRADE_PCT / 100)
    position_risk = abs(risk)
    if position_risk > entry * 0.3:
        print(f"   🔴 Risco por share (${position_risk:.2f}) > 30% do preco — stop longe demais")
        red += 1
        results.append(("Position Size", "RED", "Stop muito distante"))
    else:
        max_shares = int(max_risk_amount / position_risk)
        total_cost = max_shares * entry
        print(f"   Capital: ${capital:,.0f} | Risco maximo: ${max_risk_amount:,.0f} ({MAX_RISK_PER_TRADE_PCT}%)")
        print(f"   Max shares: {max_shares} | Custo total: ${total_cost:,.0f}")
        if total_cost > capital:
            print(f"   🟡 Custo total excede o capital — ajustar shares")
            yellow += 1
            results.append(("Position Size", "YELLOW", f"{max_shares} shares = ${total_cost:,.0f} > capital"))
        else:
            print(f"   🟢 Dentro dos limites de risco")
            green += 1
            results.append(("Position Size", "GREEN", f"{max_shares} shares, max loss ${max_risk_amount:,.0f}"))
    print()

    # ---- 3. Earnings Proximity ----
    print("3. EARNINGS PROXIMITY")
    has_earnings, earn_date = check_earnings_proximity(ticker)
    if has_earnings:
        print(f"   🔴 Earnings em {earn_date} — NUNCA entrar antes de earnings sem edge!")
        red += 1
        results.append(("Earnings", "RED", f"Earnings em {earn_date}"))
    else:
        print(f"   🟢 Sem earnings nos proximos 7 dias")
        green += 1
        results.append(("Earnings", "GREEN", "Sem earnings proximos"))
    print()

    # ---- 4. Correlation ----
    print("4. CORRELACAO COM POSICOES ABERTAS")
    positions = load_positions()
    corrs = check_correlation(ticker, positions)
    if not corrs:
        print(f"   🟢 Nenhuma posicao aberta ou dados insuficientes")
        green += 1
        results.append(("Correlation", "GREEN", "Sem posicoes abertas"))
    else:
        high_corrs = [c for c in corrs if c[2] == "HIGH"]
        med_corrs = [c for c in corrs if c[2] == "MEDIUM"]
        for c in corrs:
            icon = "🔴" if c[2] == "HIGH" else "🟡" if c[2] == "MEDIUM" else "🟢"
            print(f"   {icon} {c[0]}: r={c[1]:.2f} ({c[2]})")
        if high_corrs:
            print(f"   🔴 Alta correlacao com: {', '.join(c[0] for c in high_corrs)} — risco concentrado!")
            red += 1
            results.append(("Correlation", "RED", f"Alta correlacao com {', '.join(c[0] for c in high_corrs)}"))
        elif med_corrs:
            print(f"   🟡 Correlacao moderada — nao ideal")
            yellow += 1
            results.append(("Correlation", "YELLOW", "Correlacao moderada"))
        else:
            print(f"   🟢 Correlacao baixa — diversificacao OK")
            green += 1
            results.append(("Correlation", "GREEN", "Baixa correlacao"))
    print()

    # ---- 5. Sector Concentration ----
    print("5. CONCENTRACAO SETORIAL")
    sector, count, total, conc = check_sector_concentration(ticker, positions)
    print(f"   Setor: {sector} | Posicoes no setor: {count}/{total} ({conc*100:.0f}%)")
    if conc > 0.5:
        print(f"   🔴 Mais de 50% do portfolio no setor {sector} — DIVERSIFICA!")
        red += 1
        results.append(("Sector Conc.", "RED", f"{conc*100:.0f}% em {sector}"))
    elif conc > 0.33:
        print(f"   🟡 Concentracao significativa — evitar adicionar mais")
        yellow += 1
        results.append(("Sector Conc.", "YELLOW", f"{conc*100:.0f}% em {sector}"))
    else:
        print(f"   🟢 Concentracao OK")
        green += 1
        results.append(("Sector Conc.", "GREEN", f"{conc*100:.0f}% em {sector}"))
    print()

    # ---- 6. Technical Context ----
    print("6. CONTEXTO TECNICO RAPIDO")
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="6mo")
        if not hist.empty and len(hist) >= 50:
            close = hist["Close"]
            cp = close.iloc[-1]
            sma_20 = close.rolling(20).mean().iloc[-1]
            sma_50 = close.rolling(50).mean().iloc[-1]

            # RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0.0)
            loss = (-delta).where(delta < 0, 0.0)
            avg_gain = gain.rolling(14).mean().iloc[-1]
            avg_loss = loss.rolling(14).mean().iloc[-1]
            rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss else 50

            # Signals
            above_sma20 = cp > sma_20
            above_sma50 = cp > sma_50
            rsi_ok = 30 < rsi < 70
            above_vwap = False
            try:
                typical = (hist["High"] + hist["Low"] + hist["Close"]) / 3
                vwap = (typical.iloc[-20:] * hist["Volume"].iloc[-20:]).sum() / hist["Volume"].iloc[-20:].sum()
                above_vwap = cp > vwap
            except Exception:
                pass

            tech_score = sum([above_sma20, above_sma50, rsi_ok, above_vwap])

            lines = []
            lines.append(f"   SMA 20: {'🟢 ACIMA' if above_sma20 else '🔴 ABAIXO'}")
            lines.append(f"   SMA 50: {'🟢 ACIMA' if above_sma50 else '🔴 ABAIXO'}")
            lines.append(f"   RSI: {rsi:.0f} {'🟢' if rsi_ok else '🔴' if rsi < 30 else '🔴'}")
            if above_vwap is not None:
                lines.append(f"   VWAP: {'🟢 ACIMA' if above_vwap else '🔴 ABAIXO'}")
            for line in lines:
                print(line)

            if tech_score >= 3:
                print(f"   🟢 Contexto tecnico favoravel ({tech_score}/4)")
                green += 1
                results.append(("Technical", "GREEN", f"Score {tech_score}/4"))
            elif tech_score >= 2:
                print(f"   🟡 Contexto misto ({tech_score}/4)")
                yellow += 1
                results.append(("Technical", "YELLOW", f"Score {tech_score}/4"))
            else:
                print(f"   🔴 Contexto desfavoravel ({tech_score}/4)")
                red += 1
                results.append(("Technical", "RED", f"Score {tech_score}/4"))
        else:
            print("   ⚪ Dados insuficientes")
    except Exception as e:
        print(f"   ⚪ Erro: {e}")
    print()

    # ---- Verdict ----
    print("=" * 60)
    total_checks = green + yellow + red
    print(f"  VEREDITO: {green}G / {yellow}Y / {red}R")
    if red == 0 and yellow <= 1 and green >= 4:
        print("  🟢 APROVADO — Trade com boa estrutura")
    elif red == 0 and yellow <= 2:
        print("  🟡 CONDICIONAL — Corrige os warnings antes de entrar")
    elif red <= 1:
        print("  🟡 PRECAUCAO — Revê os red flags; ajusta stops ou sizing")
    else:
        print("  🔴 REPROVADO — Múltiplos red flags. Espera melhor setup.")
    print("=" * 60)
    print()

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Checklist pre-trade")
    parser.add_argument("ticker", help="Ticker a verificar")
    parser.add_argument("entry", type=float, help="Preco de entrada")
    parser.add_argument("stop", type=float, help="Stop loss")
    parser.add_argument("--target", "-t", type=float, help="Take profit (opcional)")
    parser.add_argument("--capital", "-c", type=float, default=5000, help="Capital da conta (default: 5000 EUR)")
    args = parser.parse_args()

    run_checklist(args.ticker.upper(), args.entry, args.stop, args.target, args.capital)


if __name__ == "__main__":
    main()
