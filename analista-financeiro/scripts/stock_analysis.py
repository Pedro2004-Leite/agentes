"""
Analise completa de stock — estilo relatorio profissional (NBIS).
Uso: python stock_analysis.py <TICKER> [--compare TICKER1,TICKER2]
Output: reports/YYYY-MM-DD/TICKER.md
"""
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).parent))
from config import get_report_path, ensure_dirs, ANOS_HISTORICOS

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("Erro: instala as dependencias primeiro")
    print("  pip install yfinance pandas numpy")
    sys.exit(1)


# ============================================================
# Helpers
# ============================================================

def fmt_b(val):
    """Formatar bilioes."""
    if val is None or pd.isna(val):
        return "N/D"
    return f"${val/1e9:.2f}B"


def fmt_m(val):
    """Formatar milhoes."""
    if val is None or pd.isna(val):
        return "N/D"
    return f"${val/1e6:.1f}M"


def fmt_pct(val):
    if val is None or pd.isna(val):
        return "N/D"
    return f"{val*100:.2f}%" if abs(val) < 10 else f"{val*100:.1f}%"


def fmt_num(val):
    if val is None or pd.isna(val):
        return "N/D"
    return f"{val:.2f}"


def safe_get(d, key, default="N/D"):
    val = d.get(key)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return val


# ============================================================
# Analise Fundamental
# ============================================================

def analyze_fundamentals(ticker):
    """Extrair e analisar dados fundamentais."""
    t = yf.Ticker(ticker)
    info = t.info

    # Financials
    revenue = info.get("totalRevenue")
    revenue_growth = info.get("revenueGrowth")
    gross_margins = info.get("grossMargins")
    ebitda = info.get("ebitda")
    ebitda_margins = info.get("ebitdaMargins")
    net_income = info.get("netIncomeToCommon")
    profit_margins = info.get("profitMargins")
    free_cashflow = info.get("freeCashflow")
    operating_cashflow = info.get("operatingCashflow")

    # Balance sheet
    total_cash = info.get("totalCash")
    total_debt = info.get("totalDebt")
    current_ratio = info.get("currentRatio")
    debt_to_equity = info.get("debtToEquity")
    book_value = info.get("bookValue")

    # Per share
    eps_trailing = info.get("trailingEps")
    eps_forward = info.get("forwardEps")

    return {
        "name": info.get("shortName", ticker),
        "sector": info.get("sector", "N/D"),
        "industry": info.get("industry", "N/D"),
        "market_cap": info.get("marketCap"),
        "employees": info.get("fullTimeEmployees"),
        "description": info.get("longBusinessSummary", "N/D"),
        # P&L
        "revenue": revenue,
        "revenue_growth": revenue_growth,
        "gross_margins": gross_margins,
        "ebitda": ebitda,
        "ebitda_margins": ebitda_margins,
        "net_income": net_income,
        "profit_margins": profit_margins,
        "free_cashflow": free_cashflow,
        "operating_cashflow": operating_cashflow,
        # Balance sheet
        "total_cash": total_cash,
        "total_debt": total_debt,
        "current_ratio": current_ratio,
        "debt_to_equity": debt_to_equity,
        "book_value": book_value,
        # Per share
        "eps_trailing": eps_trailing,
        "eps_forward": eps_forward,
        # Raw info for reference
        "info": info,
    }


# ============================================================
# Valuation
# ============================================================

def analyze_valuation(info, ticker):
    """Analise de valuation."""
    t = yf.Ticker(ticker)
    i = t.info

    pe_trailing = i.get("trailingPE")
    pe_forward = i.get("forwardPE")
    pb = i.get("priceToBook")
    ev_ebitda = i.get("enterpriseToEbitda")
    ps = i.get("priceToSales")
    peg = i.get("pegRatio")
    roe = i.get("returnOnEquity")
    roa = i.get("returnOnAssets")

    # DCF simplificado
    fcf = info.get("free_cashflow")
    shares = i.get("sharesOutstanding")
    growth_rate = info.get("revenue_growth") or 0.05
    wacc = 0.10  # Cost of capital simplificado

    dcf_value = None
    if fcf and shares and fcf > 0 and shares > 0:
        fcf_per_share = fcf / shares
        try:
            # Projecao a 5 anos + terminal value
            projections = []
            current_fcf = fcf_per_share
            g = min(max(growth_rate, 0.0), 0.25)  # growth entre 0% e 25%
            for yr in range(1, 6):
                current_fcf *= (1 + g)
                projections.append(current_fcf / ((1 + wacc) ** yr))

            # Terminal value (perpetuity com 2.5% growth)
            terminal_g = 0.025
            terminal_value = (current_fcf * (1 + terminal_g)) / (wacc - terminal_g)
            terminal_pv = terminal_value / ((1 + wacc) ** 5)

            dcf_value = sum(projections) + terminal_pv
        except Exception:
            dcf_value = None

    return {
        "pe_trailing": pe_trailing,
        "pe_forward": pe_forward,
        "pb": pb,
        "ev_ebitda": ev_ebitda,
        "ps": ps,
        "peg": peg,
        "roe": roe,
        "roa": roa,
        "dcf_value": dcf_value,
        "current_price": i.get("currentPrice") or i.get("regularMarketPreviousClose"),
    }


# ============================================================
# Peer Comparison
# ============================================================

def analyze_peers(ticker, peer_tickers):
    """Comparar metricas entre pares."""
    all_tickers = [ticker] + [p.strip() for p in peer_tickers.split(",")]
    rows = []

    for tkr in all_tickers:
        try:
            t = yf.Ticker(tkr)
            i = t.info
            rows.append({
                "Ticker": tkr,
                "Nome": i.get("shortName", tkr)[:25],
                "Market Cap": fmt_b(i.get("marketCap")),
                "P/E": fmt_num(i.get("trailingPE")),
                "P/E Fwd": fmt_num(i.get("forwardPE")),
                "P/B": fmt_num(i.get("priceToBook")),
                "EV/EBITDA": fmt_num(i.get("enterpriseToEbitda")),
                "Rev Growth": fmt_pct(i.get("revenueGrowth")),
                "Margem Bruta": fmt_pct(i.get("grossMargins")),
                "ROE": fmt_pct(i.get("returnOnEquity")),
                "D/E": fmt_num(i.get("debtToEquity")),
            })
        except Exception as e:
            rows.append({
                "Ticker": tkr, "Nome": f"Erro: {str(e)[:20]}",
                "Market Cap": "N/D", "P/E": "N/D", "P/E Fwd": "N/D",
                "P/B": "N/D", "EV/EBITDA": "N/D", "Rev Growth": "N/D",
                "Margem Bruta": "N/D", "ROE": "N/D", "D/E": "N/D",
            })

    return rows


# ============================================================
# Analise Tecnica
# ============================================================

def analyze_technicals(ticker):
    """Analise tecnica completa."""
    t = yf.Ticker(ticker)
    hist = t.history(period=f"{ANOS_HISTORICOS}y")

    if hist.empty:
        return {"error": f"Sem dados historicos para {ticker}"}

    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]
    volume = hist["Volume"]

    current_price = close.iloc[-1]

    # Medias moveis
    sma_20 = close.rolling(20).mean().iloc[-1]
    sma_50 = close.rolling(50).mean().iloc[-1]
    sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

    # MACD
    ema_12 = close.ewm(span=12).mean()
    ema_26 = close.ewm(span=26).mean()
    macd_line = ema_12 - ema_26
    signal = macd_line.ewm(span=9).mean()
    macd_hist = macd_line - signal

    macd_current = macd_line.iloc[-1]
    signal_current = signal.iloc[-1]
    macd_hist_current = macd_hist.iloc[-1]

    # MACD cross (ultimos 3 dias)
    macd_cross = None
    if len(macd_line) >= 3:
        prev_macd = macd_line.iloc[-2]
        prev_signal = signal.iloc[-2]
        if prev_macd <= prev_signal and macd_current > signal_current:
            macd_cross = "bullish"  # Golden cross
        elif prev_macd >= prev_signal and macd_current < signal_current:
            macd_cross = "bearish"  # Death cross

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi_current = rsi.iloc[-1]

    # Bollinger Bands
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    bb_upper_current = bb_upper.iloc[-1]
    bb_lower_current = bb_lower.iloc[-1]
    bb_width = ((bb_upper_current - bb_lower_current) / bb_mid.iloc[-1]) * 100

    # Suporte e Resistencia (simplificado: minimos e maximos locais)
    recent_lows = low.iloc[-60:].nsmallest(3)
    recent_highs = high.iloc[-60:].nlargest(3)
    support_levels = sorted(recent_lows.tolist())
    resistance_levels = sorted(recent_highs.tolist())

    # Volume
    avg_volume_20 = volume.iloc[-21:-1].mean() if len(volume) >= 21 else volume.mean()
    recent_volume = volume.iloc[-5:].mean()
    volume_ratio = recent_volume / avg_volume_20 if avg_volume_20 > 0 else 1

    # Tendencia
    if sma_200 and current_price > sma_200:
        trend = "Bullish (acima SMA 200)"
    elif sma_200 and current_price < sma_200:
        trend = "Bearish (abaixo SMA 200)"
    else:
        trend = "Indefinida"

    # Sinais
    signals = []
    if macd_cross == "bullish":
        signals.append("MACD cruzou acima do sinal (Golden Cross)")
    elif macd_cross == "bearish":
        signals.append("MACD cruzou abaixo do sinal (Death Cross)")
    if rsi_current < 30:
        signals.append(f"RSI oversold ({rsi_current:.1f}) — possivel bounce")
    elif rsi_current > 70:
        signals.append(f"RSI overbought ({rsi_current:.1f}) — possivel correcao")
    if volume_ratio > 1.5:
        signals.append(f"Volume {volume_ratio:.1f}x acima da media — atencao")

    return {
        "current_price": current_price,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "macd": macd_current,
        "macd_signal": signal_current,
        "macd_hist": macd_hist_current,
        "macd_cross": macd_cross,
        "rsi": rsi_current,
        "bb_upper": bb_upper_current,
        "bb_lower": bb_lower_current,
        "bb_width": bb_width,
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "volume_ratio": volume_ratio,
        "trend": trend,
        "signals": signals,
    }


# ============================================================
# News / Catalysts
# ============================================================

def get_catalysts(ticker):
    """Extrair noticias recentes como catalisadores/riscos."""
    try:
        t = yf.Ticker(ticker)
        news = t.news[:10]
        catalysts = []
        for item in news:
            title = item.get("title", "")
            if title:
                catalysts.append(title)
        return catalysts
    except Exception:
        return []


# ============================================================
# Report Generation
# ============================================================

def generate_report(ticker, peer_tickers=None):
    """Gerar relatorio completo estilo NBIS."""
    ensure_dirs()
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"  Analise Completa: {ticker.upper()}")
    print(f"  Data: {date_str}")
    print(f"{'='*60}\n")

    # 1. Dados fundamentais
    print("[1/6] A obter dados fundamentais...")
    try:
        fund = analyze_fundamentals(ticker)
    except Exception as e:
        print(f"Erro na analise fundamental: {e}")
        return

    # 2. Valuation
    print("[2/6] A calcular valuation...")
    try:
        val = analyze_valuation(fund, ticker)
    except Exception as e:
        print(f"Erro no valuation: {e}")
        val = {}

    # 3. Peer comparison
    peers_data = None
    if peer_tickers:
        print(f"[3/6] A comparar com pares: {peer_tickers}...")
        try:
            peers_data = analyze_peers(ticker, peer_tickers)
        except Exception as e:
            print(f"Erro na comparacao: {e}")

    # 4. Analise tecnica
    print("[4/6] A executar analise tecnica...")
    try:
        tech = analyze_technicals(ticker)
    except Exception as e:
        print(f"Erro na analise tecnica: {e}")
        tech = {"error": str(e)}

    # 5. Catalisadores
    print("[5/6] A obter catalisadores...")
    try:
        catalysts = get_catalysts(ticker)
    except Exception:
        catalysts = []

    # 6. Gerar relatorio
    print("[6/6] A gerar relatorio markdown...")

    L = []
    L.append(f"# {fund['name']} ({ticker.upper()}) — Analise Completa")
    L.append("")
    L.append(f"**Data:** {today.strftime('%d/%m/%Y %H:%M')} (Portugal)")
    L.append(f"**Setor:** {fund['sector']} | **Industria:** {fund['industry']}")
    L.append(f"**Market Cap:** {fmt_b(fund['market_cap'])}")
    L.append("")

    # ---- 1. Visao Geral ----
    L.append("## 1. Visao Geral da Empresa")
    L.append("")
    desc = fund.get("description", "N/D")
    if len(desc) > 600:
        desc = desc[:600] + "..."
    L.append(f"{desc}")
    L.append("")

    # ---- 2. Analise Financeira ----
    L.append("## 2. Analise Financeira")
    L.append("")
    L.append("| Metrica | Valor |")
    L.append("|---------|-------|")
    L.append(f"| Receita | {fmt_b(fund['revenue'])} |")
    L.append(f"| Crescimento Receita | {fmt_pct(fund['revenue_growth'])} |")
    L.append(f"| Margem Bruta | {fmt_pct(fund['gross_margins'])} |")
    L.append(f"| EBITDA | {fmt_b(fund['ebitda'])} |")
    L.append(f"| Margem EBITDA | {fmt_pct(fund['ebitda_margins'])} |")
    L.append(f"| Lucro Liquido | {fmt_b(fund['net_income'])} |")
    L.append(f"| Margem Liquida | {fmt_pct(fund['profit_margins'])} |")
    L.append(f"| Free Cash Flow | {fmt_b(fund['free_cashflow'])} |")
    L.append(f"| EPS (trailing) | {fmt_num(fund['eps_trailing'])} |")
    L.append(f"| EPS (forward) | {fmt_num(fund['eps_forward'])} |")
    L.append("")
    L.append("| Balanco | Valor |")
    L.append("|---------|-------|")
    L.append(f"| Cash | {fmt_b(fund['total_cash'])} |")
    L.append(f"| Divida Total | {fmt_b(fund['total_debt'])} |")
    L.append(f"| D/E | {fmt_num(fund['debt_to_equity'])} |")
    L.append(f"| Current Ratio | {fmt_num(fund['current_ratio'])} |")
    L.append(f"| Book Value/Share | {fmt_num(fund['book_value'])} |")
    L.append("")

    # ---- 3. Valuation ----
    L.append("## 3. Valuation")
    L.append("")
    L.append("| Metrica | Valor |")
    L.append("|---------|-------|")
    L.append(f"| P/E (trailing) | {fmt_num(val.get('pe_trailing'))} |")
    L.append(f"| P/E (forward) | {fmt_num(val.get('pe_forward'))} |")
    L.append(f"| P/B | {fmt_num(val.get('pb'))} |")
    L.append(f"| EV/EBITDA | {fmt_num(val.get('ev_ebitda'))} |")
    L.append(f"| P/S | {fmt_num(val.get('ps'))} |")
    L.append(f"| PEG | {fmt_num(val.get('peg'))} |")
    L.append(f"| ROE | {fmt_pct(val.get('roe'))} |")
    L.append(f"| ROA | {fmt_pct(val.get('roa'))} |")
    L.append("")

    if val.get("dcf_value") and val.get("current_price"):
        dcf = val["dcf_value"]
        price = val["current_price"]
        upside = ((dcf - price) / price) * 100
        L.append(f"**DCF (simplificado, WACC 10%):** ${dcf:.2f} por share")
        L.append(f"**Preco atual:** ${price:.2f}")
        L.append(f"**Upside/Downside:** {upside:+.1f}%")
        if upside > 20:
            L.append("⚠️ DCF indica subvalorizacao significativa (verificar pressupostos)")
        elif upside < -20:
            L.append("⚠️ DCF indica sobrevalorizacao significativa")
        L.append("")

    # ---- 4. Peer Comparison ----
    if peers_data:
        L.append("## 4. Comparacao com Pares")
        L.append("")
        headers = list(peers_data[0].keys())
        L.append("| " + " | ".join(headers) + " |")
        L.append("|" + "|".join(["--------"] * len(headers)) + "|")
        for row in peers_data:
            L.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
        L.append("")

    # ---- 5. Analise Tecnica ----
    L.append("## 5. Analise Tecnica")
    L.append("")

    if tech.get("error"):
        L.append(f"**Erro:** {tech['error']}")
    else:
        L.append(f"**Preco atual:** ${fmt_num(tech['current_price'])}")
        L.append(f"**Tendencia:** {tech['trend']}")
        L.append("")
        L.append("| Indicador | Valor | Sinal |")
        L.append("|-----------|-------|-------|")
        L.append(f"| SMA 20 | ${fmt_num(tech['sma_20'])} | {'Acima' if tech['current_price'] > tech['sma_20'] else 'Abaixo'} |")
        L.append(f"| SMA 50 | ${fmt_num(tech['sma_50'])} | {'Acima' if tech['current_price'] > tech['sma_50'] else 'Abaixo'} |")
        if tech.get('sma_200'):
            L.append(f"| SMA 200 | ${fmt_num(tech['sma_200'])} | {'Acima' if tech['current_price'] > tech['sma_200'] else 'Abaixo'} |")

        # MACD
        macd_signal_str = "Bullish" if tech['macd'] > tech['macd_signal'] else "Bearish"
        L.append(f"| MACD | {fmt_num(tech['macd'])} | {macd_signal_str} |")

        # RSI
        rsi = tech['rsi']
        if rsi < 30:
            rsi_str = f"Oversold"
        elif rsi > 70:
            rsi_str = f"Overbought"
        else:
            rsi_str = "Neutro"
        L.append(f"| RSI (14) | {rsi:.1f} | {rsi_str} |")

        L.append(f"| Bollinger Width | {tech['bb_width']:.1f}% | — |")
        L.append(f"| Volume vs Media | {tech['volume_ratio']:.1f}x | {'Alto' if tech['volume_ratio'] > 1.5 else 'Normal'} |")
        L.append("")

        if tech.get("signals"):
            L.append("### Sinais Ativos")
            for s in tech["signals"]:
                L.append(f"- {s}")
            L.append("")

        if tech.get("support_levels"):
            L.append(f"**Suportes:** " + " | ".join(f"${s:.2f}" for s in tech["support_levels"]))
            L.append("")
        if tech.get("resistance_levels"):
            L.append(f"**Resistencias:** " + " | ".join(f"${r:.2f}" for r in tech["resistance_levels"]))
            L.append("")

    # ---- 6. Catalisadores e Riscos ----
    L.append("## 6. Catalisadores e Riscos")
    L.append("")
    if catalysts:
        L.append("### Catalisadores / Noticias Recentes")
        for i, c in enumerate(catalysts[:8], 1):
            L.append(f"{i}. {c}")
    else:
        L.append("Sem noticias recentes disponiveis.")
    L.append("")
    L.append("### Riscos a Monitorizar")
    L.append("- **Risco de Mercado:** Exposicao a ciclos economicos e volatilidade do setor")
    L.append("- **Risco de Execucao:** Capacidade de atingir guidance e expectativas")
    L.append("- **Risco de Valuation:** Multiplos podem contrair mesmo com bons resultados")
    L.append("- **Risco de Liquidez:** Atencao ao spread e volume medio diario")
    L.append("")

    # ---- 7. Tese Bull/Bear ----
    L.append("## 7. Tese Bull / Bear")
    L.append("")

    L.append("### Caso Bullish 🟢")
    if fund.get("revenue_growth") and fund["revenue_growth"] > 0.1:
        L.append(f"- Crescimento de receita forte ({fmt_pct(fund['revenue_growth'])})")
    if fund.get("profit_margins") and fund["profit_margins"] > 0.15:
        L.append(f"- Margens solidas ({fmt_pct(fund['profit_margins'])})")
    if tech.get("trend") and "Bullish" in tech["trend"]:
        L.append("- Tendencia tecnica bullish (acima SMA 200)")
    if tech.get("rsi") and tech["rsi"] < 30:
        L.append("- RSI oversold — possivel ponto de entrada com boa R/R")
    L.append("- [Completar com analise qualitativa]")
    L.append("")

    L.append("### Caso Bearish 🔴")
    if fund.get("total_debt") and fund.get("total_cash"):
        if fund["total_debt"] > fund["total_cash"] * 2:
            L.append("- Divida elevada vs cash")
    if tech.get("rsi") and tech["rsi"] > 70:
        L.append("- RSI overbought — risco de correcao")
    if tech.get("trend") and "Bearish" in tech["trend"]:
        L.append("- Tendencia tecnica bearish (abaixo SMA 200)")
    L.append("- [Completar com analise qualitativa]")
    L.append("")

    # ---- 8. Niveis Tecnicos ----
    L.append("## 8. Niveis Tecnicos (para trading)")
    L.append("")
    L.append("| Tipo | Preco | Nota |")
    L.append("|------|-------|------|")

    price = tech.get("current_price", 0)
    if tech.get("resistance_levels"):
        r1 = tech["resistance_levels"][0]
        L.append(f"| Resistencia | ${r1:.2f} | Primeira resistencia |")
    L.append(f"| **Entrada** | **${price:.2f}** | Preco atual |")
    if tech.get("support_levels"):
        s1 = tech["support_levels"][0]
        L.append(f"| Suporte / Stop | ${s1:.2f} | Stop loss sugerido |")
    if tech.get("resistance_levels") and len(tech["resistance_levels"]) >= 2:
        r2 = tech["resistance_levels"][1]
        L.append(f"| Target 1 | ${r2:.2f} | Primeiro take profit |")

    L.append("")
    L.append("---")
    L.append("")
    L.append("**Disclaimer:** Esta analise e informativa, nao e recomendacao de investimento. Faz o teu proprio research. Gere o teu risco.")

    # Guardar
    output_path = get_report_path(ticker, date_str)
    report_text = "\n".join(L)
    output_path.write_text(report_text, encoding="utf-8")

    print(f"\nRelatorio guardado: {output_path}")
    print(f"\n{'='*60}")
    print(f"  Analise concluida para {ticker.upper()}")
    print(f"{'='*60}\n")

    # Print ao ecra (ignorar erros de encoding no Windows)
    try:
        print(report_text)
    except UnicodeEncodeError:
        print(report_text.encode("ascii", errors="replace").decode("ascii"))


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Analise completa de stock (estilo NBIS)"
    )
    parser.add_argument("ticker", help="Ticker a analisar (ex: AAPL)")
    parser.add_argument(
        "--compare", "-c",
        help="Tickers para peer comparison, separados por virgula (ex: MSFT,GOOGL)"
    )
    args = parser.parse_args()

    ticker = args.ticker.strip().upper()
    generate_report(ticker, args.compare)


if __name__ == "__main__":
    main()
