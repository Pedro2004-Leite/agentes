"""
Briefing matinal de mercados — EUA + Europa + FX + Earnings.
Uso: python market_briefing.py
Output: reports/YYYY-MM-DD/briefing.md
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    BENCHMARKS, WATCHLIST, MACRO_MONITORS,
    get_briefing_path, ensure_dirs,
)

try:
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

    # --- Indices ---
    print("[1/6] Indices...")
    index_data = get_index_batch(BENCHMARKS)

    # --- Macro (FX, yields, commodities) ---
    print("[2/6] Macro (FX, commodities, yields)...")
    macro_data = get_index_batch(MACRO_MONITORS)

    # --- Watchlist ---
    print("[3/6] Watchlist com RSI...")
    watchlist_data = get_watchlist_batch(WATCHLIST)

    # --- Noticias ---
    print("[4/6] Noticias...")
    news = get_market_news(WATCHLIST + ["SPY", "QQQ"])

    # --- Earnings esta semana ---
    print("[5/6] Earnings calendar...")
    earnings = get_earnings_this_week(WATCHLIST)

    # --- Gerar markdown ---
    print("[6/6] A gerar relatorio...")

    L = []
    L.append(f"# 📊 Market Briefing — {today.strftime('%d/%m/%Y')}")
    L.append("")
    L.append(f"**Hora:** {today.strftime('%H:%M')} (Portugal)")
    L.append(f"**Mercados:** Fechados" if today.weekday() >= 5 else "**Mercados:** Em sessao / Pre-market")
    L.append("")

    # ---- Resumo Executivo ----
    L.append("## 🔥 Resumo Executivo")
    L.append("")

    # Snapshot rapido dos principais indices
    us_indices = {"^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^DJI": "Dow Jones"}
    for tid, name in us_indices.items():
        if tid in index_data:
            d = index_data[tid]
            chg = fmt_pct(d["change_pct"])
            L.append(f"- **{name}:** {fmt_num(d['price'])} ({chg})")

    # VIX
    vix = index_data.get("^VIX", {})
    if vix.get("price"):
        vix_p = vix["price"]
        L.append(f"- **VIX:** {vix_p:.1f}", end="")
        if vix_p < 15:
            L[-1] += " — Complacente"
        elif vix_p < 20:
            L[-1] += " — Normal"
        elif vix_p < 30:
            L[-1] += " — ⚠️ Elevado"
        else:
            L[-1] += " — 🚨 Medo extremo"

    L.append("")

    # EUR/USD
    eurusd = macro_data.get("EURUSD=X", {})
    if eurusd.get("price"):
        L.append(f"- **EUR/USD:** {eurusd['price']:.4f} ({fmt_pct(eurusd.get('change_pct', 0))})")

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
        price = fmt_num(d.get("price"))
        chg = fmt_pct(d.get("change_pct"))
        marker = "🔴" if (d.get("change_pct") or 0) < 0 else "🟢"
        L.append(f"| {name} | {price} | {marker} {chg} |")
    L.append("")

    # ---- Indices Europa ----
    L.append("## 🇪🇺 Indices Europa")
    L.append("")
    L.append("| Indice | Preco | Variacao |")
    L.append("|--------|-------|----------|")

    eu_order = ["^STOXX50E", "^GDAXI", "^FTSE", "^FCHI", "PSI20.LS", "^V2TX"]
    for tid in eu_order:
        d = index_data.get(tid, {})
        if d.get("error"):
            continue
        name = d.get("name", tid)
        price = fmt_num(d.get("price"))
        chg = fmt_pct(d.get("change_pct"))
        marker = "🔴" if (d.get("change_pct") or 0) < 0 else "🟢"
        L.append(f"| {name} | {price} | {marker} {chg} |")
    L.append("")

    # ---- Commodities & Yields ----
    L.append("## 🛢️ Commodities & Yields")
    L.append("")
    L.append("| Ativo | Preco | Variacao |")
    L.append("|-------|-------|----------|")

    for tid in MACRO_MONITORS:
        d = macro_data.get(tid, {})
        if d.get("error"):
            continue
        name = d.get("name", tid)
        price = fmt_num(d.get("price"), 4 if "=X" in tid else 2)
        chg = fmt_pct(d.get("change_pct"))
        marker = "🔴" if (d.get("change_pct") or 0) < 0 else "🟢"
        L.append(f"| {name} | {price} | {marker} {chg} |")
    L.append("")

    # ---- Analise VIX / Sentimento ----
    L.append("## 🧠 Sentimento de Mercado")
    L.append("")

    # VIX analysis
    vix_p = vix.get("price")
    if vix_p:
        if vix_p < 15:
            L.append(f"- O VIX em {vix_p:.1f} mostra **complacencia** — mercados tranquilos, mas atencao a picos subitos.")
            L.append(f"- Ambiente favoravel a breakouts e trend following.")
        elif vix_p < 20:
            L.append(f"- VIX {vix_p:.1f} esta em territorio **normal** — volatilidade dentro do esperado.")
            L.append(f"- Bom para trades com setups tecnicos confirmados.")
        elif vix_p < 25:
            L.append(f"- VIX em {vix_p:.1f} — **volatilidade acima da media**. Cautela com position sizing.")
            L.append(f"- Stops mais largos recomendados para evitar whipsaws.")
        elif vix_p < 30:
            L.append(f"- VIX {vix_p:.1f} — **stress no mercado**. Reduzir tamanho de posicoes.")
            L.append(f"- Oportunidades de compra em pânico, mas com gestao rigorosa.")
        else:
            L.append(f"- ⚠️ VIX em {vix_p:.1f} — **medo extremo**. Mercado em panico.")
            L.append(f"- Possiveis oportunidades de reversal, mas timing e critico.")

    # VSTOXX para Europa
    vstoxx = index_data.get("^V2TX", {})
    if vstoxx.get("price"):
        v2 = vstoxx["price"]
        L.append(f"- **VSTOXX (Europa):** {v2:.1f}" +
                 (" — volatilidade europeia normal" if v2 < 25 else " — cautela na Europa"))
    L.append("")

    # ---- Watchlist ----
    if watchlist_data:
        L.append("## 📋 Watchlist")
        L.append("")
        L.append("| Ticker | Preco | Var. % | RSI | Sinal |")
        L.append("|--------|-------|--------|-----|-------|")

        for w in watchlist_data:
            price = fmt_num(w["price"])
            chg = fmt_pct(w["change_pct"])
            rsi = f"{w['rsi']:.1f}" if w.get("rsi") is not None else "N/D"
            ticker = w["ticker"]

            # Sinais
            signals = []
            if w.get("rsi"):
                if w["rsi"] < 30:
                    signals.append("OVS")
                elif w["rsi"] > 70:
                    signals.append("OVB")
            if w.get("sma_50") and w.get("price"):
                if w["price"] > w["sma_50"]:
                    signals.append("↑SMA50")
                else:
                    signals.append("↓SMA50")
            sinal_str = " ".join(signals) if signals else "—"

            L.append(f"| {ticker} | {price} | {chg} | {rsi} | {sinal_str} |")
        L.append("")

        # Destaques: top gainer, top loser
        gainers = [w for w in watchlist_data if w.get("change_pct") and w["change_pct"] > 0]
        losers = [w for w in watchlist_data if w.get("change_pct") and w["change_pct"] < 0]

        if gainers:
            top_gainer = max(gainers, key=lambda x: x["change_pct"])
            L.append(f"**🟢 Top Gainer:** {top_gainer['ticker']} ({fmt_pct(top_gainer['change_pct'])})")

        if losers:
            top_loser = min(losers, key=lambda x: x["change_pct"])
            L.append(f"**🔴 Top Loser:** {top_loser['ticker']} ({fmt_pct(top_loser['change_pct'])})")

        # OV count
        ovs = [w for w in watchlist_data if w.get("rsi") and w["rsi"] < 30]
        ovb = [w for w in watchlist_data if w.get("rsi") and w["rsi"] > 70]
        if ovs:
            L.append(f"**Oversold:** {', '.join(w['ticker'] for w in ovs)}")
        if ovb:
            L.append(f"**Overbought:** {', '.join(w['ticker'] for w in ovb)}")
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
        L.append("")
        for e in earnings:
            L.append(f"- **{e['ticker']}** ({e['name']}) — {e['date']}")
    else:
        L.append("### Earnings Reports")
        L.append("Nenhum earnings da watchlist esta semana.")
    L.append("")

    # ---- Alertas acionaveis ----
    L.append("## ⚡ Alertas Acionaveis")
    L.append("")

    alerts_found = False

    # Watchlist alerts
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

    # Print ao ecra
    try:
        print(report_text)
    except UnicodeEncodeError:
        print(report_text.encode("ascii", errors="replace").decode("ascii"))


if __name__ == "__main__":
    generate_briefing()
