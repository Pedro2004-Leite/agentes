"""
Analise completa de stock — estilo relatorio profissional.
Uso: python stock_analysis.py <TICKER> [--compare TICKER1,TICKER2] [--full]
Output: reports/YYYY-MM-DD/TICKER.md
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).parent))

# Fix Unicode emoji crash on Windows cp1252 terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import get_report_path, ensure_dirs, ANOS_HISTORICOS

try:
    import requests_cache
    requests_cache.install_cache(
        str(Path(__file__).parent / '.yfinance_cache'),
        expire_after=900,
        allowable_methods=['GET'],
    )
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("Erro: instala as dependencias primeiro")
    print("  pip install yfinance pandas numpy tabulate")
    sys.exit(1)


# ============================================================
# Helpers
# ============================================================

def fmt_b(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"${val/1e9:.2f}B"


def fmt_m(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"${val/1e6:.1f}M"


def fmt_pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"{val*100:.2f}%" if abs(val) < 10 else f"{val*100:.1f}%"


def fmt_num(val, decimals=2):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"{val:.{decimals}f}"


def safe_get(d, key, default="N/D"):
    val = d.get(key)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    return val


def fmt_billions_or_millions(val):
    """Formata para B se >1B, M caso contrario."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    if abs(val) >= 1e9:
        return f"${val/1e9:.2f}B"
    return f"${val/1e6:.1f}M"


# ============================================================
# Analise Fundamental
# ============================================================

def analyze_fundamentals(ticker):
    """Extrair e analisar dados fundamentais."""
    t = yf.Ticker(ticker)
    info = t.info

    # Income
    revenue = info.get("totalRevenue")
    revenue_growth = info.get("revenueGrowth")
    gross_margins = info.get("grossMargins")
    gross_profits = info.get("grossProfits")
    ebitda = info.get("ebitda")
    ebitda_margins = info.get("ebitdaMargins")
    net_income = info.get("netIncomeToCommon")
    profit_margins = info.get("profitMargins")
    free_cashflow = info.get("freeCashflow")
    operating_cashflow = info.get("operatingCashflow")

    # Balance sheet
    total_cash = info.get("totalCash")
    total_debt = info.get("totalDebt")
    net_debt = info.get("netDebt")
    current_ratio = info.get("currentRatio")
    debt_to_equity = info.get("debtToEquity")
    book_value = info.get("bookValue")
    total_assets = info.get("totalAssets")

    # Per share
    eps_trailing = info.get("trailingEps")
    eps_forward = info.get("forwardEps")
    dividend_yield = info.get("dividendYield")
    # yfinance returns dividendYield as percentage (0.36 = 0.36%), convert to decimal
    if dividend_yield is not None:
        dividend_yield = dividend_yield / 100.0
    dividend_rate = info.get("dividendRate")
    payout_ratio = info.get("payoutRatio")

    # Growth estimates
    earnings_growth = info.get("earningsGrowth")
    earnings_quarterly_growth = info.get("earningsQuarterlyGrowth")

    return {
        "name": info.get("shortName", ticker),
        "sector": info.get("sector", "N/D"),
        "industry": info.get("industry", "N/D"),
        "market_cap": info.get("marketCap"),
        "enterprise_value": info.get("enterpriseValue"),
        "employees": info.get("fullTimeEmployees"),
        "description": info.get("longBusinessSummary", "N/D"),
        # P&L
        "revenue": revenue,
        "revenue_growth": revenue_growth,
        "gross_profits": gross_profits,
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
        "net_debt": net_debt,
        "current_ratio": current_ratio,
        "debt_to_equity": debt_to_equity,
        "book_value": book_value,
        "total_assets": total_assets,
        # Per share
        "eps_trailing": eps_trailing,
        "eps_forward": eps_forward,
        "dividend_yield": dividend_yield,
        "dividend_rate": dividend_rate,
        "payout_ratio": payout_ratio,
        # Growth
        "earnings_growth": earnings_growth,
        "earnings_quarterly_growth": earnings_quarterly_growth,
        # Raw data
        "info": info,
    }


# ============================================================
# Advanced Metrics (quarterly, earnings history, insider)
# ============================================================

def analyze_advanced(ticker):
    """Extrair dados avancados: quarterly trends, earnings beat rate, insider trading."""
    t = yf.Ticker(ticker)
    result = {}

    # -- Quarterly revenue & earnings trend --
    try:
        q_income = t.quarterly_income_stmt
        if q_income is not None and not q_income.empty:
            result["quarterly_revenue"] = q_income.loc["Total Revenue"].tolist()[:4] if "Total Revenue" in q_income.index else []
            result["quarterly_net_income"] = q_income.loc["Net Income"].tolist()[:4] if "Net Income" in q_income.index else []
            result["quarterly_dates"] = [str(d.date()) for d in q_income.columns[:4]]
    except Exception:
        result["quarterly_revenue"] = []
        result["quarterly_net_income"] = []
        result["quarterly_dates"] = []

    # -- Earnings beat rate --
    try:
        earnings_hist = t.earnings_history
        if earnings_hist is not None and not earnings_hist.empty:
            beats = (earnings_hist["epsActual"] > earnings_hist["epsEstimate"]).sum()
            total = len(earnings_hist)
            beat_rate = beats / total if total > 0 else None
            result["earnings_beat_rate"] = beat_rate
            result["earnings_total_quarters"] = total
            result["earnings_beats"] = beats
        else:
            result["earnings_beat_rate"] = None
    except Exception:
        result["earnings_beat_rate"] = None

    # -- EPS estimate revisions --
    try:
        eps_trend = t.eps_trend
        if eps_trend is not None and not eps_trend.empty:
            result["eps_trend"] = eps_trend.to_dict()
    except Exception:
        result["eps_trend"] = None

    try:
        eps_rev = t.eps_revisions
        if eps_rev is not None and not eps_rev.empty:
            result["eps_revisions"] = eps_rev.to_dict()
    except Exception:
        result["eps_revisions"] = None

    # -- Insider transactions --
    try:
        insider = t.insider_transactions
        if insider is not None and not insider.empty:
            recent = insider.head(10)
            total_buys = (recent["startDate"].notna()).sum() if "startDate" in recent.columns else 0
            result["insider_transactions"] = recent.to_dict()
            result["insider_recent_count"] = len(recent)
        else:
            result["insider_transactions"] = None
    except Exception:
        result["insider_transactions"] = None

    # -- Analyst recommendation trend --
    try:
        recs = t.recommendations
        if recs is not None and not recs.empty:
            result["recommendation_trend"] = {
                "recent": recs.head(5).to_dict() if len(recs) >= 5 else recs.to_dict(),
                "count": len(recs),
            }
    except Exception:
        result["recommendation_trend"] = None

    return result


# ============================================================
# Valuation
# ============================================================

def analyze_valuation(fund, ticker):
    """Analise de valuation com DCF + sensibilidade."""
    t = yf.Ticker(ticker)
    i = t.info

    pe_trailing = i.get("trailingPE")
    pe_forward = i.get("forwardPE")
    pb = i.get("priceToBook")
    ev_ebitda = i.get("enterpriseToEbitda")
    ev_revenue = i.get("enterpriseToRevenue")
    ps = i.get("priceToSales")
    peg = i.get("pegRatio")
    roe = i.get("returnOnEquity")
    roa = i.get("returnOnAssets")
    roce = i.get("returnOnCapitalEmployed")

    # Beta
    beta = i.get("beta")

    # Short interest
    short_pct = i.get("shortPercentOfFloat")
    short_ratio = i.get("shortRatio")  # Days to cover
    shares_short = i.get("sharesShort")

    # Institutional
    inst_held = i.get("heldPercentInstitutions")
    insider_held = i.get("heldPercentInsiders")

    # Analyst targets
    target_mean = i.get("targetMeanPrice")
    target_high = i.get("targetHighPrice")
    target_low = i.get("targetLowPrice")
    num_analysts = i.get("numberOfAnalystOpinions")
    rec_mean = i.get("recommendationMean")  # 1=Strong Buy, 5=Sell

    # Implied volatility (from options, pode falhar)
    implied_vol = None
    try:
        if t.options:
            atm_strike = round(i.get("currentPrice", 100))
            opt_chain = t.option_chain(t.options[0])
            calls = opt_chain.calls
            # Procurar opcao ATM mais proxima
            atm_row = calls.iloc[(calls["strike"] - atm_strike).abs().argsort()[:1]]
            if not atm_row.empty:
                implied_vol = atm_row["impliedVolatility"].values[0]
    except Exception:
        pass

    current_price = i.get("currentPrice") or i.get("regularMarketPreviousClose")

    # ---- DCF com sensibilidade ----
    fcf = fund.get("free_cashflow")
    shares = i.get("sharesOutstanding")
    # Usar earnings growth como proxy para FCF growth (nao revenue growth)
    # Se nao disponivel, usa revenue_growth com haircut de 20%
    earn_g = fund.get("earnings_growth")
    rev_g = fund.get("revenue_growth")
    if earn_g is not None and not (isinstance(earn_g, float) and np.isnan(earn_g)):
        growth_rate = earn_g
    elif rev_g is not None and not (isinstance(rev_g, float) and np.isnan(rev_g)):
        growth_rate = rev_g * 0.8  # FCF cresce mais devagar que revenue
    else:
        growth_rate = 0.05

    dcf_scenarios = {}
    if fcf and shares and fcf > 0 and shares > 0:
        fcf_per_share = fcf / shares
        base_growth = min(max(growth_rate, 0.0), 0.25)

        for scenario, (g, wacc, term_g) in {
            "Bull": (base_growth + 0.03, 0.09, 0.030),
            "Base": (base_growth, 0.10, 0.025),
            "Bear": (max(base_growth - 0.03, 0.0), 0.12, 0.020),
        }.items():
            try:
                projections = []
                cf = fcf_per_share
                g_adj = min(g, 0.25)
                # Verificar que WACC > term_g (condicao necessaria para perpetuity)
                if wacc <= term_g:
                    dcf_scenarios[scenario] = None
                    continue
                for yr in range(1, 6):
                    cf *= (1 + g_adj)
                    projections.append(cf / ((1 + wacc) ** yr))
                terminal_value = (cf * (1 + term_g)) / (wacc - term_g)
                terminal_pv = terminal_value / ((1 + wacc) ** 5)
                dcf_scenarios[scenario] = sum(projections) + terminal_pv
            except Exception:
                dcf_scenarios[scenario] = None

    return {
        "pe_trailing": pe_trailing,
        "pe_forward": pe_forward,
        "pb": pb,
        "ev_ebitda": ev_ebitda,
        "ev_revenue": ev_revenue,
        "ps": ps,
        "peg": peg,
        "roe": roe,
        "roa": roa,
        "roce": roce,
        "beta": beta,
        "short_pct": short_pct,
        "short_ratio": short_ratio,
        "shares_short": shares_short,
        "inst_held": inst_held,
        "insider_held": insider_held,
        "target_mean": target_mean,
        "target_high": target_high,
        "target_low": target_low,
        "num_analysts": num_analysts,
        "rec_mean": rec_mean,
        "implied_vol": implied_vol,
        "dcf_scenarios": dcf_scenarios,
        "current_price": current_price,
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
                "Beta": fmt_num(i.get("beta")),
            })
        except Exception:
            rows.append({k: "N/D" for k in [
                "Ticker", "Nome", "Market Cap", "P/E", "P/E Fwd",
                "P/B", "EV/EBITDA", "Rev Growth", "Margem Bruta",
                "ROE", "D/E", "Beta"
            ]})
            rows[-1]["Ticker"] = tkr
            rows[-1]["Nome"] = "Erro"

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

    # ---- Medias moveis ----
    sma_20 = close.rolling(20).mean().iloc[-1]
    sma_50 = close.rolling(50).mean().iloc[-1]
    sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

    # ---- MACD ----
    ema_12 = close.ewm(span=12).mean()
    ema_26 = close.ewm(span=26).mean()
    macd_line = ema_12 - ema_26
    signal = macd_line.ewm(span=9).mean()
    macd_hist = macd_line - signal
    macd_current = macd_line.iloc[-1]
    signal_current = signal.iloc[-1]
    macd_hist_current = macd_hist.iloc[-1]

    # MACD cross (3 dias)
    macd_cross = None
    if len(macd_line) >= 3:
        prev_m = macd_line.iloc[-2]
        prev_s = signal.iloc[-2]
        if prev_m <= prev_s and macd_current > signal_current:
            macd_cross = "bullish"
        elif prev_m >= prev_s and macd_current < signal_current:
            macd_cross = "bearish"

    # ---- RSI ----
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi_current = rsi.iloc[-1]

    # ---- Bollinger Bands ----
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_upper_current = bb_upper.iloc[-1]
    bb_lower_current = bb_lower.iloc[-1]
    bb_width = ((bb_upper_current - bb_lower_current) / bb_mid.iloc[-1]) * 100

    # Bollinger squeeze (BW < 5% — minimo 6 meses)
    bb_squeeze = bb_width < 5

    # ---- ATR (Average True Range) ----
    atr_period = 14
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(atr_period).mean()
    atr_current = atr.iloc[-1]
    atr_pct = (atr_current / current_price) * 100

    # ---- ADX (Average Directional Index) ----
    adx_period = 14
    plus_dm = high.diff().where(high.diff() > low.diff().abs(), 0)
    minus_dm = low.diff().abs().where(low.diff().abs() > high.diff(), 0)
    atr_adx = true_range.rolling(adx_period).mean()
    plus_di = 100 * (plus_dm.rolling(adx_period).mean() / atr_adx)
    minus_di = 100 * (minus_dm.rolling(adx_period).mean() / atr_adx)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.rolling(adx_period).mean()
    adx_current = adx.iloc[-1]

    # ---- Suporte e Resistencia ----
    recent_lows = low.iloc[-60:].nsmallest(3)
    recent_highs = high.iloc[-60:].nlargest(3)
    support_levels = sorted(recent_lows.tolist())
    resistance_levels = sorted(recent_highs.tolist())

    # ---- Volume ----
    avg_volume_20 = volume.iloc[-21:-1].mean() if len(volume) >= 21 else volume.mean()
    recent_volume = volume.iloc[-5:].mean()
    volume_ratio = recent_volume / avg_volume_20 if avg_volume_20 > 0 else 1

    # ---- VWAP aproximado (20 dias) ----
    typical_price = (high + low + close) / 3
    vwap_20 = (typical_price.iloc[-20:] * volume.iloc[-20:]).sum() / volume.iloc[-20:].sum() \
        if volume.iloc[-20:].sum() > 0 else current_price

    # ---- Performance periodos ----
    perf = {}
    for label, days in [("1 semana", 5), ("1 mes", 21), ("3 meses", 63), ("6 meses", 126), ("1 ano", 252)]:
        if len(close) > days:
            perf[label] = ((current_price - close.iloc[-days]) / close.iloc[-days]) * 100
        else:
            perf[label] = None

    # ---- Tendencia ----
    if sma_200 and current_price > sma_200:
        trend = "Bullish (acima SMA 200)"
    elif sma_200 and current_price < sma_200:
        trend = "Bearish (abaixo SMA 200)"
    else:
        trend = "Indefinida" if not sma_200 else "Sem dados suficientes"

    # ---- Sinais ----
    signals = []
    warnings = []

    if macd_cross == "bullish":
        signals.append("✅ MACD bullish cross — momentum positivo")
    elif macd_cross == "bearish":
        signals.append("❌ MACD bearish cross — momentum negativo")
    else:
        if macd_current > signal_current:
            signals.append("MACD acima do sinal (bullish)")
        else:
            warnings.append("MACD abaixo do sinal")

    if rsi_current < 30:
        signals.append(f"🔵 RSI oversold ({rsi_current:.1f}) — possivel bounce")
    elif rsi_current > 70:
        warnings.append(f"🔴 RSI overbought ({rsi_current:.1f}) — risco de correcao")
    elif 30 <= rsi_current <= 40:
        signals.append(f"RSI ({rsi_current:.1f}) na zona baixa — atencao a suporte")

    if volume_ratio > 1.5:
        signals.append(f"📊 Volume {volume_ratio:.1f}x media — interesse institucional possivel")
    elif volume_ratio < 0.5:
        warnings.append("Volume muito baixo — cuidado com slippage")

    if adx_current > 25:
        if plus_di.iloc[-1] > minus_di.iloc[-1]:
            signals.append(f"ADX {adx_current:.1f} — tendencia bullish forte")
        else:
            signals.append(f"ADX {adx_current:.1f} — tendencia bearish forte")
    elif adx_current < 20:
        signals.append(f"ADX {adx_current:.1f} — mercado lateral, prefere range trading")

    if bb_squeeze:
        signals.append("🔶 Bollinger squeeze — breakout iminente")

    # Preco vs VWAP
    if current_price > vwap_20:
        signals.append(f"Preco acima do VWAP 20d — vies bullish")
    else:
        warnings.append("Preco abaixo do VWAP 20d")

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
        "bb_squeeze": bb_squeeze,
        "atr": atr_current,
        "atr_pct": atr_pct,
        "adx": adx_current,
        "vwap_20": vwap_20,
        "perf": perf,
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "volume_ratio": volume_ratio,
        "trend": trend,
        "signals": signals,
        "warnings": warnings,
    }


# ============================================================
# News / Catalysts
# ============================================================

def get_catalysts(ticker):
    """Extrair noticias recentes como catalisadores/riscos."""
    try:
        t = yf.Ticker(ticker)
        news = t.news[:15]
        catalysts = []
        for item in news:
            title = item.get("title", "").strip()
            if title:
                catalysts.append(title)
        return catalysts
    except Exception:
        return []


# ============================================================
# Report Generation
# ============================================================

def generate_report(ticker, peer_tickers=None, full=False):
    """Gerar relatorio completo estilo institutional research."""
    ensure_dirs()
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"  Analise Completa: {ticker.upper()}")
    print(f"  Data: {date_str}")
    print(f"{'='*60}\n")

    # 1. Fundamentais
    print("[1/6] Dados fundamentais...")
    try:
        fund = analyze_fundamentals(ticker)
    except Exception as e:
        print(f"Erro: {e}")
        return

    # 2. Valuation
    print("[2/6] Valuation + short interest + targets...")
    try:
        val = analyze_valuation(fund, ticker)
    except Exception as e:
        print(f"Erro no valuation: {e}")
        val = {}

    # 2b. Advanced metrics
    print("[2b/6] Quarterly data + earnings history + insider...")
    try:
        adv = analyze_advanced(ticker)
    except Exception as e:
        print(f"Erro advanced: {e}")
        adv = {}

    # 3. Peers
    peers_data = None
    if peer_tickers:
        print(f"[3/6] Analise de pares: {peer_tickers}...")
        try:
            peers_data = analyze_peers(ticker, peer_tickers)
        except Exception as e:
            print(f"Erro: {e}")

    # 4. Tecnica
    print("[4/6] Analise tecnica...")
    try:
        tech = analyze_technicals(ticker)
    except Exception as e:
        print(f"Erro: {e}")
        tech = {"error": str(e)}

    # 5. Catalisadores
    print("[5/6] Catalisadores...")
    try:
        catalysts = get_catalysts(ticker)
    except Exception:
        catalysts = []

    # 6. Gerar relatorio
    print("[6/6] Gerar relatorio...")

    L = []
    price = tech.get("current_price", val.get("current_price", 0))

    # ---- Cabecalho ----
    L.append(f"# {fund['name']} ({ticker.upper()}) — Relatorio de Analise")
    L.append("")
    L.append(f"**Data:** {today.strftime('%d/%m/%Y %H:%M')} (Portugal)")
    L.append(f"**Preco atual:** ${price:.2f}" if price else "**Preco atual:** N/D")
    L.append(f"**Setor:** {fund['sector']} | **Industria:** {fund['industry']}")
    L.append(f"**Market Cap:** {fmt_b(fund['market_cap'])} | **EV:** {fmt_b(fund.get('enterprise_value'))}")
    L.append("")

    # ---- 1. Visao Geral ----
    L.append("## 1. Visao Geral da Empresa")
    L.append("")
    desc = fund.get("description", "N/D")
    if len(desc) > 800:
        desc = desc[:800].rsplit(".", 1)[0] + "."
    L.append(desc)
    L.append("")

    # Key stats rapido
    L.append("### Key Stats")
    L.append("")
    L.append(f"- **Empregados:** {fund.get('employees', 'N/D'):,}" if isinstance(fund.get('employees'), (int, float)) else f"- **Empregados:** {fund.get('employees')}")
    L.append(f"- **Beta:** {fmt_num(val.get('beta'))}")
    L.append(f"- **Dividendo:** Yield {fmt_pct(fund.get('dividend_yield'))} | Rate {fmt_num(fund.get('dividend_rate'), 2)}")
    L.append(f"- **Payout Ratio:** {fmt_pct(fund.get('payout_ratio'))}")
    L.append("")

    # ---- 2. Analise Financeira ----
    L.append("## 2. Analise Financeira")
    L.append("")
    L.append("### Income Statement (ultimo fiscal year)")
    L.append("")
    L.append("| Metrica | Valor |")
    L.append("|---------|-------|")
    L.append(f"| Receita | {fmt_b(fund['revenue'])} |")
    L.append(f"| Crescimento de Receita (YoY) | {fmt_pct(fund['revenue_growth'])} |")
    L.append(f"| Lucro Bruto | {fmt_b(fund.get('gross_profits'))} |")
    L.append(f"| Margem Bruta | {fmt_pct(fund['gross_margins'])} |")
    L.append(f"| EBITDA | {fmt_b(fund['ebitda'])} |")
    L.append(f"| Margem EBITDA | {fmt_pct(fund['ebitda_margins'])} |")
    L.append(f"| Lucro Liquido | {fmt_b(fund['net_income'])} |")
    L.append(f"| Margem Liquida | {fmt_pct(fund['profit_margins'])} |")
    L.append(f"| Free Cash Flow | {fmt_b(fund['free_cashflow'])} |")
    L.append(f"| Operating Cash Flow | {fmt_b(fund.get('operating_cashflow'))} |")
    L.append(f"| EPS (trailing) | {fmt_num(fund['eps_trailing'])} |")
    L.append(f"| EPS (forward) | {fmt_num(fund['eps_forward'])} |")
    L.append("")

    # Growth
    earn_g = fund.get("earnings_growth")
    earn_q = fund.get("earnings_quarterly_growth")
    if earn_g or earn_q:
        L.append(f"**Crescimento de Earnings:** Anual {fmt_pct(earn_g)} | Trimestral {fmt_pct(earn_q)}")
        L.append("")

    # Balance sheet
    L.append("### Balance Sheet")
    L.append("")
    L.append("| Metrica | Valor |")
    L.append("|---------|-------|")
    L.append(f"| Cash & Equivalentes | {fmt_b(fund['total_cash'])} |")
    L.append(f"| Divida Total | {fmt_b(fund['total_debt'])} |")
    L.append(f"| Net Debt | {fmt_b(fund.get('net_debt'))} |")
    L.append(f"| D/E Ratio | {fmt_num(fund['debt_to_equity'])} |")
    L.append(f"| Current Ratio | {fmt_num(fund['current_ratio'])} |")
    L.append(f"| Book Value / Share | {fmt_num(fund['book_value'])} |")

    # Health check
    de = fund.get("debt_to_equity")
    cr = fund.get("current_ratio")
    if de is not None and de > 2:
        L.append("")
        L.append("⚠️ **D/E elevado** — alavancagem acima do confortavel.")
    if cr is not None and cr < 1.0:
        L.append("")
        L.append("⚠️ **Current Ratio < 1** — potenciais problemas de liquidez de curto prazo.")

    L.append("")

    # ---- 2b. Quarterly Trends + Earnings History ----
    if adv:
        q_rev = adv.get("quarterly_revenue", [])
        q_dates = adv.get("quarterly_dates", [])
        if q_rev and len(q_rev) >= 2:
            L.append("### Tendencia Trimestral de Receita")
            L.append("")
            L.append("| Periodo | Receita |")
            L.append("|---------|---------|")
            for i, rev in enumerate(q_rev[:4]):
                date_str = q_dates[i] if i < len(q_dates) else f"Q{i+1}"
                L.append(f"| {date_str} | {fmt_b(rev)} |")
            # Crescimento QoQ
            if len(q_rev) >= 2:
                qoq = ((q_rev[0] - q_rev[1]) / abs(q_rev[1])) * 100 if q_rev[1] != 0 else 0
                L.append(f"**Crescimento QoQ:** {qoq:+.1f}%")
            L.append("")

        # Earnings beat rate
        beat_rate = adv.get("earnings_beat_rate")
        if beat_rate is not None:
            beats = adv.get("earnings_beats", 0)
            total = adv.get("earnings_total_quarters", 0)
            L.append("### Earnings Beat Rate")
            L.append("")
            if total > 0:
                L.append(f"- **{beats}/{total}** quarters acima do estimado (**{beat_rate*100:.0f}%** beat rate)")
                if beat_rate > 0.75:
                    L.append("- 🟢 Bate estimativas consistentemente — quality signal forte")
                elif beat_rate > 0.5:
                    L.append("- 🟡 Beat rate medio — sem vantagem informacional clara")
                else:
                    L.append("- 🔴 Raramente bate estimativas — guidance pode ser agressivo ou execucao fraca")
            L.append("")

        # EPS revisions
        eps_trend = adv.get("eps_trend")
        if eps_trend:
            L.append("### EPS Estimate Revisions")
            L.append("")
            # Get current quarter estimate trend
            current_key = next((k for k in eps_trend.keys() if "current" in str(k).lower()), None)
            if current_key:
                trend_data = eps_trend[current_key]
                if isinstance(trend_data, dict):
                    periods = sorted(trend_data.keys(), reverse=True)[:3]
                    if periods:
                        values = [trend_data.get(p) for p in periods if trend_data.get(p) is not None]
                        if len(values) >= 2:
                            direction = "🟢 Upward" if values[0] > values[-1] else "🔴 Downward"
                            L.append(f"- **Revisao de estimativas:** {direction}")
            L.append("")

        # Insider transactions
        insider = adv.get("insider_transactions")
        if insider:
            L.append("### Insider Trading (Recente)")
            L.append("")
            # Parse insider transactions
            insider_count = adv.get("insider_recent_count", 0)
            if insider_count > 0:
                L.append(f"- {insider_count} transacoes de insiders recentes")
                # Try to summarize buys vs sells
                L.append("- (_Ver transacoes detalhadas no terminal: `Ticker.insider_transactions`_)")
            L.append("")

    # ---- 3. Valuation ----
    L.append("## 3. Valuation")
    L.append("")
    L.append("### Multiplos")
    L.append("")
    L.append("| Metrica | Valor | Interpretacao |")
    L.append("|---------|-------|---------------|")

    pe_t = val.get("pe_trailing")
    pe_f = val.get("pe_forward")
    ev_eb = val.get("ev_ebitda")

    def pe_note(pe):
        if pe is None or np.isnan(pe):
            return "N/D"
        if pe < 0:
            return "Prejuizo"
        if pe < 15:
            return "Barato"
        if pe < 25:
            return "Razoavel"
        if pe < 35:
            return "Caro"
        return "Muito caro"

    L.append(f"| P/E (trailing) | {fmt_num(pe_t)} | {pe_note(pe_t)} |")
    L.append(f"| P/E (forward) | {fmt_num(pe_f)} | {pe_note(pe_f)} |")
    L.append(f"| P/B | {fmt_num(val.get('pb'))} | |")
    L.append(f"| EV/EBITDA | {fmt_num(ev_eb)} | {'Barato' if ev_eb and ev_eb < 12 else 'Razoavel' if ev_eb and ev_eb < 20 else 'Caro' if ev_eb else 'N/D'} |")
    L.append(f"| EV/Revenue | {fmt_num(val.get('ev_revenue'))} | |")
    L.append(f"| P/S | {fmt_num(val.get('ps'))} | |")
    L.append(f"| PEG Ratio | {fmt_num(val.get('peg'))} | {'Subvalorizado' if val.get('peg') and val['peg'] < 1 else 'Sobrevalorizado' if val.get('peg') and val['peg'] > 2 else 'N/D'} |")
    L.append(f"| ROE | {fmt_pct(val.get('roe'))} | |")
    L.append(f"| ROA | {fmt_pct(val.get('roa'))} | |")
    L.append(f"| ROCE | {fmt_pct(val.get('roce'))} | |")
    L.append("")

    # DCF scenarios
    dcf = val.get("dcf_scenarios", {})
    current = val.get("current_price") or tech.get("current_price")
    if dcf and current:
        L.append("### DCF — Cenarios")
        L.append("")
        L.append("| Scenario | Fair Value | Upside/Downside |")
        L.append("|----------|------------|-----------------|")
        for scenario, dcf_val in dcf.items():
            if dcf_val:
                upside = ((dcf_val - current) / current) * 100
                L.append(f"| {scenario} | ${dcf_val:.2f} | {upside:+.1f}% |")
        L.append("")

    # Analyst consensus
    target = val.get("target_mean")
    if target and current:
        upside = ((target - current) / current) * 100
        L.append("### Consenso de Analistas")
        L.append("")
        L.append(f"- **Target medio:** ${target:.2f} (upside de {upside:+.1f}%)")
        L.append(f"- **Target high:** ${val.get('target_high', 0):.2f}" if val.get("target_high") else "")
        L.append(f"- **Target low:** ${val.get('target_low', 0):.2f}" if val.get("target_low") else "")
        L.append(f"- **Nº analistas:** {val.get('num_analysts', 'N/D')}")
        rec = val.get("rec_mean")
        if rec:
            rec_str = {1: "Strong Buy", 1.5: "Buy", 2: "Buy", 2.5: "Hold", 3: "Hold", 3.5: "Underperform", 4: "Sell", 5: "Strong Sell"}
            nearest = min(rec_str.keys(), key=lambda k: abs(k - rec))
            L.append(f"- **Recomendacao:** {rec_str[nearest]} ({rec:.1f})")
        L.append("")

    # Short interest
    L.append("### Sentimento de Mercado")
    L.append("")
    L.append(f"- **Short Interest:** {fmt_pct(val.get('short_pct'))} do float")
    L.append(f"- **Days to Cover:** {fmt_num(val.get('short_ratio'))} dias")
    L.append(f"- **Institucionais:** {fmt_pct(val.get('inst_held'))} | **Insiders:** {fmt_pct(val.get('insider_held'))}")
    if val.get("implied_vol"):
        L.append(f"- **Implied Volatility (ATM):** {val['implied_vol']*100:.1f}%")
    short_pct = val.get("short_pct")
    if short_pct is not None and short_pct > 0.10:
        L.append("")
        L.append(f"⚠️ **Short interest elevado ({short_pct*100:.1f}%)** — possibilidade de short squeeze se houver catalisador positivo.")
    L.append("")

    # ---- 4. Peer Comparison ----
    if peers_data:
        L.append("## 4. Comparacao com Pares")
        L.append("")
        headers = list(peers_data[0].keys())
        L.append("| " + " | ".join(headers) + " |")
        L.append("|" + "|".join(["--------"] * len(headers)) + "|")
        for row in peers_data:
            L.append("| " + " | ".join(str(row.get(h, "N/D")) for h in headers) + " |")
        L.append("")

    # ---- 5. Analise Tecnica ----
    L.append("## 5. Analise Tecnica")
    L.append("")

    if tech.get("error"):
        L.append(f"**Erro:** {tech['error']}")
    else:
        L.append(f"**Preco atual:** ${tech['current_price']:.2f}")
        L.append(f"**Tendencia:** {tech['trend']}")
        L.append("")

        L.append("### Indicadores")
        L.append("")
        L.append("| Indicador | Valor | Sinal |")
        L.append("|-----------|-------|-------|")

        sma20_s = "Acima" if tech['current_price'] > tech['sma_20'] else "Abaixo"
        sma50_s = "Acima" if tech['current_price'] > tech['sma_50'] else "Abaixo"
        L.append(f"| SMA 20 | ${tech['sma_20']:.2f} | {sma20_s} |")
        L.append(f"| SMA 50 | ${tech['sma_50']:.2f} | {sma50_s} |")

        if tech.get('sma_200'):
            sma200_s = "Acima" if tech['current_price'] > tech['sma_200'] else "Abaixo"
            L.append(f"| SMA 200 | ${tech['sma_200']:.2f} | {sma200_s} |")

        macd_s = "Bullish" if tech['macd'] > tech['macd_signal'] else "Bearish"
        L.append(f"| MACD | {tech['macd']:.4f} | {macd_s} |")
        L.append(f"| MACD Histogram | {tech['macd_hist']:.4f} | {'Positivo' if tech['macd_hist'] > 0 else 'Negativo'} |")

        rsi_v = tech['rsi']
        if rsi_v < 30:
            rsi_s = "Oversold"
        elif rsi_v > 70:
            rsi_s = "Overbought"
        elif rsi_v > 50:
            rsi_s = "Bullish"
        else:
            rsi_s = "Bearish"
        L.append(f"| RSI (14) | {rsi_v:.1f} | {rsi_s} |")

        L.append(f"| Bollinger Width | {tech['bb_width']:.1f}% | {'Squeeze' if tech.get('bb_squeeze') else 'Normal'} |")
        L.append(f"| ATR (14) | ${tech['atr']:.2f} ({tech['atr_pct']:.1f}%) | |")
        L.append(f"| ADX (14) | {tech['adx']:.1f} | {'Tendencia' if tech['adx'] > 25 else 'Lateral'} |")
        L.append(f"| VWAP (20d) | ${tech['vwap_20']:.2f} | {'Acima' if tech['current_price'] > tech['vwap_20'] else 'Abaixo'} |")
        L.append(f"| Volume vs Media | {tech['volume_ratio']:.1f}x | {'Alto' if tech['volume_ratio'] > 1.5 else 'Normal'} |")
        L.append("")

        # Sinais & warnings
        if tech.get("signals"):
            L.append("### Sinais")
            for s in tech["signals"]:
                L.append(f"- {s}")
            L.append("")

        if tech.get("warnings"):
            L.append("### Alertas")
            for w in tech["warnings"]:
                L.append(f"- {w}")
            L.append("")

        # Performance
        perf = tech.get("perf", {})
        if perf:
            L.append("### Performance")
            L.append("")
            L.append("| Periodo | Retorno |")
            L.append("|---------|---------|")
            for label, pct in perf.items():
                if pct is not None:
                    L.append(f"| {label} | {pct:+.2f}% |")
            L.append("")

        # Niveis
        if tech.get("support_levels"):
            L.append(f"**🟢 Suportes:** " + " | ".join(f"${s:.2f}" for s in tech["support_levels"][:3]))
            L.append("")
        if tech.get("resistance_levels"):
            L.append(f"**🔴 Resistencias:** " + " | ".join(f"${r:.2f}" for r in tech["resistance_levels"][:3]))
            L.append("")

    # ---- 6. Catalisadores e Riscos ----
    L.append("## 6. Catalisadores e Riscos")
    L.append("")
    if catalysts:
        L.append("### Noticias Recentes")
        for i, c in enumerate(catalysts[:10], 1):
            L.append(f"{i}. {c}")
    else:
        L.append("Sem noticias recentes disponiveis.")
    L.append("")

    L.append("### Riscos a Monitorizar")
    L.append("")
    L.append("| Risco | Descricao |")
    L.append("|-------|-----------|")
    L.append("| **Risco de Mercado** | Exposicao a ciclos economicos, taxas de juro e volatilidade do setor |")
    L.append("| **Risco de Execucao** | Capacidade de bater guidance, lancar produtos, gerir custos |")
    L.append("| **Risco de Valuation** | Multiplos podem contrair mesmo com bons fundamentais (rate expansion/contraction) |")
    L.append("| **Risco de Liquidez** | Spread, volume, slippage, impacto de fecho de posicao |")
    L.append("| **Risco Regulatorio** | Alteracoes fiscais, antitrust, restricoes setoriais |")
    L.append("")

    # ---- 7. Tese Bull/Bear ----
    L.append("## 7. Tese Bull / Bear")
    L.append("")

    L.append("### 🟢 Caso Bullish")
    L.append("")
    bull_points = 0
    if fund.get("revenue_growth") and fund["revenue_growth"] > 0.05:
        L.append(f"- Crescimento de receita solido ({fmt_pct(fund['revenue_growth'])})")
        bull_points += 1
    if fund.get("profit_margins") and fund["profit_margins"] > 0.10:
        L.append(f"- Margens saudaveis ({fmt_pct(fund['profit_margins'])}) — pricing power")
        bull_points += 1
    if tech.get("trend") and "Bullish" in tech["trend"]:
        L.append("- Acao em tendencia bullish (acima SMA 200) — momentum a favor")
        bull_points += 1
    if tech.get("rsi") and tech["rsi"] < 30:
        L.append("- RSI oversold — oportunidade de entrada com R/R favoravel")
        bull_points += 1
    if val.get("dcf_scenarios", {}).get("Base"):
        dcf_val = val["dcf_scenarios"]["Base"]
        if current and dcf_val > current * 1.1:
            L.append(f"- DCF sugere upside de {((dcf_val-current)/current)*100:.0f}% no cenario base")
            bull_points += 1
    if val.get("short_pct") and val["short_pct"] > 0.15:
        L.append(f"- Short interest elevado ({val['short_pct']*100:.1f}%) — potencial short squeeze")
        bull_points += 1
    if fund.get("free_cashflow") and fund["free_cashflow"] > 0:
        L.append("- FCF positivo — nao depende de financiamento externo")
        bull_points += 1
    L.append("")

    L.append("### 🔴 Caso Bearish")
    L.append("")
    bear_points = 0
    de = fund.get("debt_to_equity")
    if de and de > 1.5:
        L.append(f"- Divida elevada (D/E {de:.1f}) — vulneravel a subida de taxas")
        bear_points += 1
    if val.get("pe_trailing") and val["pe_trailing"] and val["pe_trailing"] > 50:
        L.append(f"- P/E de {val['pe_trailing']:.1f}x — paga-se caro pelo crescimento")
        bear_points += 1
    if tech.get("rsi") and tech["rsi"] > 70:
        L.append("- RSI overbought — risco de correcao no curto prazo")
        bear_points += 1
    if tech.get("trend") and "Bearish" in tech["trend"]:
        L.append("- Acao abaixo da SMA 200 — tendencia bearish estrutural")
        bear_points += 1
    if val.get("dcf_scenarios", {}).get("Base"):
        dcf_val = val["dcf_scenarios"]["Base"]
        if current and dcf_val < current * 0.9:
            L.append(f"- DCF sugere sobrevalorizacao (upside negativo)")
            bear_points += 1
    if fund.get("free_cashflow") and fund["free_cashflow"] < 0:
        L.append("- FCF negativo — queima de caixa; diluicao ou endividamento no horizonte")
        bear_points += 1
    L.append("")

    # Veredito esquematico
    L.append("### Balanco")
    L.append("")
    L.append(f"- **Argumentos Bull:** {bull_points}")
    L.append(f"- **Argumentos Bear:** {bear_points}")
    if bull_points > bear_points:
        L.append("- **Veredito:** Vies bullish — confirmar com setup tecnico para entrada.")
    elif bear_points > bull_points:
        L.append("- **Veredito:** Vies bearish — cautela; esperar confirmacao antes de entrar.")
    else:
        L.append("- **Veredito:** Neutro — tese nao conclusiva. Definir niveis e esperar.")
    L.append("")

    # ---- 8. Niveis Tecnicos ----
    L.append("## 8. Niveis Tecnicos (para trading)")
    L.append("")

    current_price = tech.get("current_price", price)
    supports = tech.get("support_levels", [])
    resistances = tech.get("resistance_levels", [])
    atr_v = tech.get("atr", current_price * 0.02)

    L.append("| Tipo | Preco | Nota |")
    L.append("|------|-------|------|")

    # Resistances
    for i, r in enumerate(resistances[:3]):
        label = f"Resistencia {i+1}"
        L.append(f"| {label} | ${r:.2f} | |")

    L.append(f"| **Entrada** | **${current_price:.2f}** | Preco atual |")

    # Supports
    for i, s in enumerate(supports[:3]):
        if i == 0:
            L.append(f"| Suporte 1 / Stop | ${s:.2f} | Stop loss sugerido |")
        else:
            L.append(f"| Suporte {i+1} | ${s:.2f} | |")

    # Target suggestion based on resistance or ATR
    if resistances:
        target_1 = resistances[0]
        risk = current_price - supports[0] if supports else atr_v
        reward = target_1 - current_price
        rr = reward / risk if risk > 0 else 0
        L.append(f"| Target 1 | ${target_1:.2f} | R/R: 1:{rr:.1f} |")

    if len(resistances) >= 2:
        target_2 = resistances[1]
        risk = current_price - supports[0] if supports else atr_v
        reward = target_2 - current_price
        rr = reward / risk if risk > 0 else 0
        L.append(f"| Target 2 | ${target_2:.2f} | R/R: 1:{rr:.1f} |")

    L.append("")

    # Position sizing suggestion
    if atr_v and current_price:
        risk_pct = (atr_v * 2) / current_price * 100
        L.append(f"**ATR-based stop distance:** ${atr_v*2:.2f} ({risk_pct:.1f}% do preco)")
        L.append(f"**Nota:** Com 2% de risco maximo da conta, dimensionar posicao de acordo.")
    L.append("")

    L.append("---")
    L.append("")
    L.append("**Disclaimer:** Esta analise e exclusivamente informativa. Nao constitui recomendacao de compra ou venda. Faz o teu proprio research. Gere o teu risco rigorosamente.")

    # Guardar
    output_path = get_report_path(ticker, date_str)
    report_text = "\n".join(L)
    output_path.write_text(report_text, encoding="utf-8")

    print(f"\nRelatorio guardado: {output_path}")
    print(f"\n{'='*60}")
    print(f"  Analise concluida para {ticker.upper()}")
    print(f"{'='*60}\n")

    try:
        print(report_text)
    except UnicodeEncodeError:
        print(report_text.encode("ascii", errors="replace").decode("ascii"))


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Analise completa de stock (estilo institucional)")
    parser.add_argument("ticker", help="Ticker a analisar (ex: AAPL)")
    parser.add_argument("--compare", "-c", help="Tickers para peer comparison, separados por virgula")
    parser.add_argument("--full", action="store_true", help="Relatorio completo com todas as seccoes")
    args = parser.parse_args()

    ticker = args.ticker.strip().upper()
    generate_report(ticker, args.compare, args.full)


if __name__ == "__main__":
    main()
