"""
Briefing matinal de mercados — EUA + Europa + FX + Earnings.
Uso: python market_briefing.py
Output: reports/YYYY-MM-DD/briefing.md
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Fix Unicode emoji crash on Windows cp1252 terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import (
    BENCHMARKS, WATCHLIST, MACRO_MONITORS,
    YIELD_TICKERS, FUTURES_TICKERS, SECTOR_ETFS,
    get_briefing_path, ensure_dirs,
)

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

def fmt_pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"{val:+.2f}%"


def fmt_num(val, decimals=2):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"{val:.{decimals}f}"


def fmt_b(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"${val/1e9:.2f}B"


# ============================================================
# Data fetching
# ============================================================

def get_ticker_data(ticker, period="5d"):
    """Obter dados de um ticker com tratamento de erro."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period=period)

        if hist.empty or len(hist) < 2:
            return {
                "ticker": ticker,
                "name": info.get("shortName", ticker),
                "price": info.get("regularMarketPreviousClose"),
                "change_pct": None,
                "volume": None,
                "hist": hist,
                "info": info,
            }

        today_close = hist["Close"].iloc[-1]
        prev_close = hist["Close"].iloc[-2]
        change_pct = ((today_close - prev_close) / prev_close) * 100
        volume = hist["Volume"].iloc[-1] if "Volume" in hist.columns else None

        return {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "price": today_close,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "volume": volume,
            "market_cap": info.get("marketCap"),
            "hist": hist,
            "info": info,
        }
    except Exception as e:
        return {
            "ticker": ticker,
            "name": ticker,
            "price": None,
            "change_pct": None,
            "error": str(e),
        }


def get_index_batch(tickers):
    """Obter dados de varios indices."""
    results = {}
    for ticker in tickers:
        data = get_ticker_data(ticker)
        results[ticker] = data
    return results


def get_watchlist_batch(tickers):
    """Obter dados da watchlist com RSI rapido."""
    results = []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            hist = t.history(period="1mo")

            if hist.empty or len(hist) < 2:
                continue

            close = hist["Close"]
            price = close.iloc[-1]
            prev = close.iloc[-2]
            change_pct = ((price - prev) / prev) * 100
            volume = hist["Volume"].iloc[-1] if "Volume" in hist.columns else None

            # RSI rapido (14 dias)
            delta = close.diff()
            gain = delta.where(delta > 0, 0.0)
            loss = (-delta).where(delta < 0, 0.0)
            avg_gain = gain.rolling(14).mean().iloc[-1]
            avg_loss = loss.rolling(14).mean().iloc[-1]
            rsi = 50
            if avg_loss and not np.isnan(avg_loss):
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

            # SMA 50 se disponivel
            sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None

            results.append({
                "ticker": ticker,
                "name": info.get("shortName", ticker),
                "price": price,
                "change_pct": change_pct,
                "volume": volume,
                "market_cap": info.get("marketCap"),
                "rsi": rsi,
                "sma_50": sma_50,
            })
        except Exception:
            continue

    # Ordenar: maiores quedas primeiro (atenção), depois maiores ganhos
    results.sort(key=lambda x: x["change_pct"] if x["change_pct"] is not None else -999)
    return results


def get_market_news(tickers=None, limit=12):
    """Obter noticias relevantes de mercado."""
    all_news = []
    sources = tickers if tickers else ["SPY", "QQQ", "IWM", "EEM"]

    for ticker in sources[:6]:
        try:
            t = yf.Ticker(ticker)
            news = t.news
            for item in news[:5]:
                title = item.get("title", "").strip()
                if title and not any(n["title"] == title for n in all_news):
                    all_news.append({
                        "title": title,
                        "link": item.get("link", ""),
                        "publisher": item.get("publisher", "N/D"),
                    })
        except Exception:
            pass

    return all_news[:limit]


def get_earnings_this_week(watchlist=None):
    """Identificar earnings reports esta semana para tickers da watchlist."""
    today = datetime.now()
    week_end = today + timedelta(days=7)
    upcoming = []

    tickers_to_check = watchlist if watchlist else []
    for ticker in tickers_to_check[:10]:
        try:
            t = yf.Ticker(ticker)
            # Tentar obter proxima data de earnings do info
            earnings_date = t.info.get("earningsTimestamp")
            earnings_date_start = t.info.get("earningsTimestampStart")
            earnings_date_end = t.info.get("earningsTimestampEnd")

            # Converter timestamp para datetime
            for ed in [earnings_date, earnings_date_start, earnings_date_end]:
                if ed:
                    ed_dt = datetime.fromtimestamp(ed)
                    if today <= ed_dt <= week_end:
                        upcoming.append({
                            "ticker": ticker,
                            "name": t.info.get("shortName", ticker),
                            "date": ed_dt.strftime("%d/%m"),
                        })
                        break
        except Exception:
            pass

    return upcoming


# ============================================================
# Report Generation
# ============================================================

def generate_briefing():
    """Gerar o briefing matinal completo."""
    ensure_dirs()
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")

    print(f"Briefing {date_str} — a gerar...\n")

    # --- Data fetching ---
    print("[1/8] Indices...")
    index_data = get_index_batch(BENCHMARKS)

    print("[2/8] Futures pre-market...")
    futures_data = get_index_batch(FUTURES_TICKERS)

    print("[3/8] Macro (FX, commodities)...")
    macro_data = get_index_batch(MACRO_MONITORS)

    print("[4/8] Yield curve...")
    yield_data = get_index_batch(YIELD_TICKERS)

    print("[5/8] Sector ETFs...")
    sector_data = get_index_batch(list(SECTOR_ETFS.keys()))

    print("[6/8] Watchlist com RSI...")
    watchlist_data = get_watchlist_batch(WATCHLIST)

    print("[7/8] Noticias...")
    news = get_market_news(WATCHLIST + ["SPY", "QQQ"])

    print("[8/8] Earnings calendar...")
    earnings = get_earnings_this_week(WATCHLIST)

    # --- Gerar markdown ---
    print("A gerar relatorio...")

    vix = index_data.get("^VIX", {})

    L = []
    L.append(f"# 📊 Market Briefing — {today.strftime('%d/%m/%Y')}")
    L.append("")
    L.append(f"**Hora:** {today.strftime('%H:%M')} (Portugal)")
    L.append(f"**Mercados:** Fechados" if today.weekday() >= 5 else "**Mercados:** Em sessao / Pre-market")
    L.append("")

    # ---- Resumo Executivo ----
    L.append("## 🔥 Resumo Executivo")
    L.append("")

    # Futures direction (pre-market)
    futures_labels = {"ES=F": "S&P 500 Fut", "NQ=F": "NASDAQ Fut", "RTY=F": "Russell Fut", "YM=F": "Dow Fut"}
    for tid, label in futures_labels.items():
        d = futures_data.get(tid, {})
        if d.get("change_pct") is not None:
            chg = fmt_pct(d["change_pct"])
            marker = "🟢" if d.get("change_pct", 0) > 0 else "🔴" if d.get("change_pct", 0) < 0 else "⚪"
            L.append(f"- **{label}:** {marker} {chg}")

    # US indices snapshot
    us_indices = {"^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^DJI": "Dow Jones", "^RUT": "Russell 2000"}
    for tid, name in us_indices.items():
        d = index_data.get(tid, {})
        if d.get("price"):
            chg = fmt_pct(d.get("change_pct"))
            L.append(f"- **{name}:** {fmt_num(d['price'])} ({chg})")

    # VIX
    if vix.get("price"):
        vix_p = vix["price"]
        if vix_p < 15: regime = "Complacente"
        elif vix_p < 20: regime = "Normal"
        elif vix_p < 25: regime = "⚠️ Elevado"
        elif vix_p < 30: regime = "🚨 Stress"
        else: regime = "🔥 Panico"
        L.append(f"- **VIX:** {vix_p:.1f} — {regime}")

    # Yield curve
    try:
        y2 = yield_data.get("^IRX", {}).get("price")  # 13-week ~= 2Y equivalent
        y10 = yield_data.get("^TNX", {}).get("price")  # 10Y
        if y2 and y10:
            spread = y10 - y2
            spread_str = f"{spread:.2f}%"
            if spread < 0:
                L.append(f"- **2Y-10Y Spread:** {spread_str} 🔴 INVERTIDA — risco de recessao")
            elif spread < 0.5:
                L.append(f"- **2Y-10Y Spread:** {spread_str} — curva achatada")
            else:
                L.append(f"- **2Y-10Y Spread:** {spread_str} — curva normal")
    except Exception:
        pass

    # EUR/USD
    eurusd = macro_data.get("EURUSD=X", {})
    if eurusd.get("price"):
        L.append(f"- **EUR/USD:** {eurusd['price']:.4f} ({fmt_pct(eurusd.get('change_pct', 0))})")

    L.append("")

    # ---- Futures Pre-Market ----
    L.append("## 🕐 Futures (Pre-Market)")
    L.append("")
    L.append("| Contrato | Preco | Var. | Sinal |")
    L.append("|----------|-------|------|-------|")

    for tid, label in futures_labels.items():
        d = futures_data.get(tid, {})
        price = fmt_num(d.get("price"))
        chg = fmt_pct(d.get("change_pct"))
        if d.get("change_pct", 0) > 0:
            signal = "🟢 Bullish" if d.get("change_pct", 0) > 0.5 else "🟢 Ligeiro"
        elif d.get("change_pct", 0) < 0:
            signal = "🔴 Bearish" if d.get("change_pct", 0) < -0.5 else "🔴 Ligeiro"
        else:
            signal = "⚪ Flat"
        L.append(f"| {label} | {price} | {chg} | {signal} |")
    L.append("")

    # ---- Indices EUA ----
    L.append("## 🇺🇸 Indices EUA")
    L.append("")
    L.append("| Indice | Preco | Variacao |")
    L.append("|--------|-------|----------|")

    us_order = ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX"]
    for tid in us_order:
        d = index_data.get(tid, {})
        name = d.get("name", tid)
        price = fmt_num(d.get("price"), 4 if tid == "^VIX" else 2)
        chg = fmt_pct(d.get("change_pct"))
        marker = "🔴" if (d.get("change_pct") or 0) < 0 else "🟢"
        L.append(f"| {name} | {price} | {marker} {chg} |")
    L.append("")

    # ---- Indices Europa ----
    L.append("## 🇪🇺 Indices Europa")
    L.append("")
    L.append("| Indice | Preco | Variacao |")
    L.append("|--------|-------|----------|")

    for tid in ["^STOXX50E", "^GDAXI", "^FTSE", "^FCHI", "PSI20.LS"]:
        d = index_data.get(tid, {})
        if d.get("error"): continue
        name = d.get("name", tid)
        price = fmt_num(d.get("price"))
        chg = fmt_pct(d.get("change_pct"))
        marker = "🔴" if (d.get("change_pct") or 0) < 0 else "🟢"
        L.append(f"| {name} | {price} | {marker} {chg} |")
    L.append("")

    # ---- Yield Curve ----
    L.append("## 📈 Yield Curve")
    L.append("")
    L.append("| Maturidade | Yield |")
    L.append("|------------|-------|")

    yield_labels = {"^IRX": "3 Meses", "^FVX": "5 Anos", "^TNX": "10 Anos", "^TYX": "30 Anos"}
    yields_present = {}
    for tid, label in yield_labels.items():
        d = yield_data.get(tid, {})
        if d.get("price"):
            yields_present[tid] = d["price"]
            L.append(f"| {label} | {d['price']:.2f}% |")

    # Spreads
    if len(yields_present) >= 2:
        L.append("")
        L.append("**Spreads:**")
        if "^IRX" in yields_present and "^TNX" in yields_present:
            spread_2_10 = yields_present["^TNX"] - yields_present["^IRX"]
            inv = " (INVERTIDA)" if spread_2_10 < 0 else ""
            L.append(f"- 3M-10Y: {spread_2_10:.2f}%{inv}")
        if "^TNX" in yields_present and "^TYX" in yields_present:
            spread_10_30 = yields_present["^TYX"] - yields_present["^TNX"]
            L.append(f"- 10Y-30Y: {spread_10_30:.2f}%")
    L.append("")

    # ---- Sector ETF Rotation ----
    L.append("## 🏗️ Sectores (Rotacao)")
    L.append("")
    L.append("| Setor | Ticker | Preco | 1 Semana | 1 Mes |")
    L.append("|-------|--------|-------|----------|-------|")

    sector_perf = []
    for tid, sector_name in SECTOR_ETFS.items():
        d = sector_data.get(tid, {})
        if d.get("error"): continue
        price = fmt_num(d.get("price"))

        # Get 1W and 1M performance from history
        perf_1w = "N/D"
        perf_1m = "N/D"
        try:
            t = yf.Ticker(tid)
            h = t.history(period="1mo")
            if len(h) >= 21:
                cp = h["Close"].iloc[-1]
                w1 = h["Close"].iloc[-6] if len(h) >= 6 else h["Close"].iloc[0]
                m1 = h["Close"].iloc[0]
                perf_1w = f"{((cp-w1)/w1)*100:+.1f}%"
                perf_1m = f"{((cp-m1)/m1)*100:+.1f}%"
        except Exception:
            pass

        L.append(f"| {sector_name} | {tid} | {price} | {perf_1w} | {perf_1m} |")

        # Store for sorting
        try:
            pct_val = float(perf_1m.replace("+", "").replace("%", ""))
        except (ValueError, AttributeError):
            pct_val = 0
        sector_perf.append((pct_val, sector_name))

    L.append("")

    # Sector highlights
    if sector_perf:
        sector_perf.sort(reverse=True)
        top_sectors = [s[1] for s in sector_perf[:3]]
        bottom_sectors = [s[1] for s in sector_perf[-3:]]
        L.append(f"**🟢 Lideres:** {', '.join(top_sectors)}")
        L.append(f"**🔴 Atrasados:** {', '.join(bottom_sectors)}")
        L.append("")

    # ---- Commodities & Yields ----
    L.append("## 🛢️ Commodities & FX")
    L.append("")
    L.append("| Ativo | Preco | Variacao |")
    L.append("|-------|-------|----------|")

    for tid in MACRO_MONITORS:
        d = macro_data.get(tid, {})
        if d.get("error"): continue
        name = d.get("name", tid)
        price = fmt_num(d.get("price"), 4 if "=X" in tid else 2)
        chg = fmt_pct(d.get("change_pct"))
        marker = "🔴" if (d.get("change_pct") or 0) < 0 else "🟢"
        L.append(f"| {name} | {price} | {marker} {chg} |")
    L.append("")

    # ---- Analise VIX / Sentimento ----
    L.append("## 🧠 Sentimento de Mercado")
    L.append("")

    vix_p = vix.get("price")
    if vix_p:
        if vix_p < 15:
            L.append(f"- O VIX em {vix_p:.1f} mostra **complacencia** — mercados tranquilos, mas atencao a picos subitos.")
        elif vix_p < 20:
            L.append(f"- VIX {vix_p:.1f} esta em territorio **normal** — volatilidade dentro do esperado.")
        elif vix_p < 25:
            L.append(f"- VIX em {vix_p:.1f} — **volatilidade acima da media**. Cautela com position sizing.")
        elif vix_p < 30:
            L.append(f"- VIX {vix_p:.1f} — **stress no mercado**. Reduzir tamanho de posicoes.")
        else:
            L.append(f"- ⚠️ VIX em {vix_p:.1f} — **medo extremo**. Mercado em panico.")

    L.append("")

    # ---- Watchlist ----
    if watchlist_data:
        L.append("## 📋 Watchlist")
        L.append("")
        L.append("| Ticker | Preco | Var. % | RSI | vs SMA50 | Niveis Chave |")
        L.append("|--------|-------|--------|-----|----------|-------------|")

        for w in watchlist_data:
            price = fmt_num(w["price"])
            chg = fmt_pct(w["change_pct"])
            rsi = f"{w['rsi']:.1f}" if w.get("rsi") is not None else "N/D"

            # vs SMA50
            sma_str = "—"
            if w.get("sma_50") and w.get("price"):
                diff = ((w["price"] - w["sma_50"]) / w["sma_50"]) * 100
                sma_str = f"{diff:+.1f}%"

            # Key levels (nearest support/resistance from recent data)
            key_levels = "—"
            try:
                t = yf.Ticker(w["ticker"])
                h = t.history(period="1mo")
                if not h.empty and len(h) >= 20:
                    current = h["Close"].iloc[-1]
                    highs = h["High"].iloc[-20:].nlargest(2).tolist()
                    lows = h["Low"].iloc[-20:].nsmallest(2).tolist()
                    if highs and lows:
                        nearest_res = min([x for x in highs if x > current], default=None)
                        nearest_sup = max([x for x in lows if x < current], default=None)
                        parts = []
                        if nearest_sup: parts.append(f"S:{nearest_sup:.2f}")
                        if nearest_res: parts.append(f"R:{nearest_res:.2f}")
                        key_levels = " | ".join(parts) if parts else "—"
            except Exception:
                pass

            L.append(f"| {w['ticker']} | {price} | {chg} | {rsi} | {sma_str} | {key_levels} |")
        L.append("")

        # Destaques
        gainers = [w for w in watchlist_data if w.get("change_pct") and w["change_pct"] > 0]
        losers = [w for w in watchlist_data if w.get("change_pct") and w["change_pct"] < 0]
        if gainers:
            top_g = max(gainers, key=lambda x: x["change_pct"])
            L.append(f"**🟢 Top Gainer:** {top_g['ticker']} ({fmt_pct(top_g['change_pct'])})")
        if losers:
            top_l = min(losers, key=lambda x: x["change_pct"])
            L.append(f"**🔴 Top Loser:** {top_l['ticker']} ({fmt_pct(top_l['change_pct'])})")
        ovs = [w for w in watchlist_data if w.get("rsi") and w["rsi"] < 30]
        ovb = [w for w in watchlist_data if w.get("rsi") and w["rsi"] > 70]
        if ovs: L.append(f"**Oversold:** {', '.join(w['ticker'] for w in ovs)}")
        if ovb: L.append(f"**Overbought:** {', '.join(w['ticker'] for w in ovb)}")
        L.append("")

    # ---- Noticias ----
    if news:
        L.append("## 📰 Principais Noticias")
        L.append("")
        for i, n in enumerate(news, 1):
            publisher = n.get("publisher", "N/D")
            L.append(f"{i}. **{n['title']}** — _{publisher}_")
        L.append("")

    # ---- Earnings esta semana ----
    L.append("## 📅 Eventos da Semana")
    L.append("")
    if earnings:
        L.append("### Earnings Reports (Watchlist)")
        for e in earnings:
            L.append(f"- **{e['ticker']}** ({e['name']}) — {e['date']}")
    else:
        L.append("Nenhum earnings da watchlist esta semana.")
    L.append("")

    # ---- Alertas acionaveis ----
    L.append("## ⚡ Alertas Acionaveis")
    L.append("")
    alerts_found = False

    for w in watchlist_data:
        if w.get("rsi") and w["rsi"] < 30:
            L.append(f"- **{w['ticker']}** em oversold (RSI {w['rsi']:.1f}) — ver se ha suporte e catalisador para entrada.")
            alerts_found = True
        if w.get("rsi") and w["rsi"] > 70:
            L.append(f"- **{w['ticker']}** em overbought (RSI {w['rsi']:.1f}) — rever stops ou considerar tomar lucro.")
            alerts_found = True

    if not alerts_found:
        L.append("Sem alertas criticos na watchlist hoje. Monitorizar setups habituais.")

    L.append("")
    L.append("---")
    L.append("")
    L.append("**Disclaimer:** Este briefing e informativo. Nao substitui o teu proprio research e risk management.")

    # Guardar
    output_path = get_briefing_path(date_str)
    report_text = "\n".join(L)
    output_path.write_text(report_text, encoding="utf-8")

    print(f"Briefing guardado: {output_path}")
    print()

    try:
        print(report_text)
    except UnicodeEncodeError:
        print(report_text.encode("ascii", errors="replace").decode("ascii"))


if __name__ == "__main__":
    generate_briefing()
