"""
Briefing matinal de mercados.
Uso: python market_briefing.py
Output: reports/YYYY-MM-DD/briefing.md
"""
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Adicionar script dir ao path para importar config
sys.path.insert(0, str(Path(__file__).parent))
from config import BENCHMARKS, WATCHLIST, get_briefing_path, ensure_dirs

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Erro: instala as dependencias primeiro")
    print("  pip install yfinance pandas")
    sys.exit(1)


def fmt_pct(val):
    """Formatar percentagem."""
    if val is None or pd.isna(val):
        return "N/D"
    return f"{val:+.2f}%"


def fmt_num(val, decimals=2):
    """Formatar numero."""
    if val is None or pd.isna(val):
        return "N/D"
    return f"{val:.{decimals}f}"


def get_index_data(tickers):
    """Obter dados dos indices."""
    data = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            hist = t.history(period="5d")
            name = info.get("shortName", ticker)

            if len(hist) >= 2:
                today_close = hist["Close"].iloc[-1]
                prev_close = hist["Close"].iloc[-2]
                change = today_close - prev_close
                change_pct = (change / prev_close) * 100
            else:
                today_close = prev_close = change = change_pct = None

            data[ticker] = {
                "name": name,
                "price": today_close,
                "change": change,
                "change_pct": change_pct,
                "info": info,
            }
        except Exception as e:
            data[ticker] = {
                "name": ticker,
                "price": None,
                "change": None,
                "change_pct": None,
                "error": str(e),
            }
    return data


def get_market_news(tickers, limit=10):
    """Obter noticias relevantes."""
    all_news = []
    tickers_to_check = tickers if tickers else ["SPY", "QQQ"]

    for ticker in tickers_to_check[:5]:  # Limitar para nao abusar da API
        try:
            t = yf.Ticker(ticker)
            news = t.news
            for item in news[:5]:
                title = item.get("title", "")
                link = item.get("link", "")
                publisher = item.get("publisher", "")
                # Evitar duplicados por titulo
                if title and not any(n["title"] == title for n in all_news):
                    all_news.append({
                        "title": title,
                        "link": link,
                        "publisher": publisher,
                    })
        except Exception:
            pass

    # Ordenar por relevancia (assumimos que a API ja ordena)
    return all_news[:limit]


def get_watchlist_data(tickers):
    """Obter dados da watchlist."""
    data = []
    if not tickers:
        return data

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            hist = t.history(period="5d")

            if len(hist) >= 2:
                today_close = hist["Close"].iloc[-1]
                prev_close = hist["Close"].iloc[-2]
                change_pct = ((today_close - prev_close) / prev_close) * 100
                volume = hist["Volume"].iloc[-1]
            else:
                today_close = prev_close = change_pct = volume = None

            data.append({
                "ticker": ticker,
                "name": info.get("shortName", ticker),
                "price": today_close,
                "change_pct": change_pct,
                "volume": volume,
                "market_cap": info.get("marketCap"),
            })
        except Exception as e:
            data.append({
                "ticker": ticker,
                "name": ticker,
                "price": None,
                "change_pct": None,
                "error": str(e),
            })
    return data


def generate_briefing():
    """Gerar o briefing matinal completo."""
    ensure_dirs()
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")

    print(f"A gerar briefing para {date_str}...")
    print("A obter dados dos indices...")
    indices = get_index_data(BENCHMARKS)

    print("A obter noticias...")
    all_tickers = WATCHLIST + ["SPY", "QQQ", "IWM"]
    news = get_market_news(all_tickers)

    print("A verificar watchlist...")
    watchlist_data = get_watchlist_data(WATCHLIST)

    # Gerar relatorio markdown
    lines = []
    lines.append(f"# Market Briefing — {today.strftime('%d/%m/%Y')}")
    lines.append("")
    lines.append(f"Gerado em {today.strftime('%H:%M')} (Portugal)")
    lines.append("")

    # Indices
    lines.append("## Indices")
    lines.append("")
    lines.append("| Indice | Preco | Variacao |")
    lines.append("|--------|-------|----------|")
    for ticker, d in indices.items():
        price = fmt_num(d["price"])
        chg = fmt_pct(d["change_pct"])
        name = d["name"]
        lines.append(f"| {name} ({ticker}) | {price} | {chg} |")
    lines.append("")

    # Sinais de mercado
    lines.append("## Sinais de Mercado")
    lines.append("")

    # VIX
    if "^VIX" in indices:
        vix = indices["^VIX"].get("price")
        if vix:
            if vix < 15:
                vix_msg = f"VIX a {vix:.1f} — mercado complacente. Atencao a reversoes."
            elif vix < 20:
                vix_msg = f"VIX a {vix:.1f} — volatilidade normal."
            elif vix < 30:
                vix_msg = f"VIX a {vix:.1f} — volatilidade elevada. Cautela."
            else:
                vix_msg = f"VIX a {vix:.1f} — medo extremo. Oportunidades ou armadilhas."
            lines.append(f"- **VIX**: {vix_msg}")
    lines.append("")

    # Watchlist
    if watchlist_data:
        lines.append("## Watchlist")
        lines.append("")
        lines.append("| Ticker | Nome | Preco | Var. | Volume |")
        lines.append("|--------|------|-------|------|--------|")
        for w in watchlist_data:
            price = fmt_num(w["price"])
            chg = fmt_pct(w["change_pct"])
            vol = f"{w['volume']:,.0f}" if w.get("volume") and not pd.isna(w["volume"]) else "N/D"
            lines.append(f"| {w['ticker']} | {w['name']} | {price} | {chg} | {vol} |")
        lines.append("")

    # Noticias
    if news:
        lines.append("## Principais Noticias")
        lines.append("")
        for i, n in enumerate(news, 1):
            publisher = n["publisher"] if n["publisher"] else "Fonte desconhecida"
            lines.append(f"{i}. **{n['title']}** _{publisher}_")
        lines.append("")

    # Proximos eventos (esta semana)
    lines.append("## Eventos da Semana")
    lines.append("")
    lines.append("_(Verificar calendario de earnings e dados economicos)_")
    lines.append("")

    output_path = get_briefing_path(date_str)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Briefing guardado: {output_path}")
    print("")
    print("=" * 50)
    print("\n".join(lines))


if __name__ == "__main__":
    generate_briefing()
