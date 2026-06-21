"""
Value Screener — screening por criterios fundamentais (valuation, qualidade, crescimento).
Uso:
  python value_screener.py --deep-value
  python value_screener.py --quality
  python value_screener.py --growth
  python value_screener.py --dividend-value
  python value_screener.py --pe-under 15 --roe-over 20 --de-under 0.5
  python value_screener.py --universe nasdaq100 --quality
  python value_screener.py --universe "AAPL,MSFT,NVDA,TSLA" --all
"""
import sys
from pathlib import Path
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps

sys.path.insert(0, str(Path(__file__).parent))

# Fix Unicode emoji crash on Windows cp1252 terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import DEFAULT_SCREENER_UNIVERSE, ensure_dirs

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
    from tabulate import tabulate
except ImportError:
    print("Erro: instala as dependencias primeiro")
    print("  pip install yfinance pandas numpy tabulate requests-cache")
    sys.exit(1)

# Reuse universe functions from screener
from screener import (
    get_sp500_tickers, get_nasdaq100_tickers, get_eurostoxx50_tickers,
    get_universe,
)


# ============================================================
# Helpers
# ============================================================

def fmt_pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"{val*100:.1f}%" if abs(val) < 10 else f"{val*100:.1f}%"


def fmt_num(val, decimals=2):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"{val:.{decimals}f}"


def fmt_b(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/D"
    return f"${val/1e9:.1f}B" if abs(val) >= 1e9 else f"${val/1e6:.0f}M"


def safe_div(a, b):
    """Safe division, returns None if division by zero."""
    if a is None or b is None or b == 0:
        return None
    return a / b


# ============================================================
# Retry decorator
# ============================================================

def retry(tries=3, delay=1, backoff=2):
    """Retry decorator with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _tries, _delay = tries, delay
            while _tries > 0:
                try:
                    return func(*args, **kwargs)
                except Exception:
                    _tries -= 1
                    if _tries == 0:
                        raise
                    time.sleep(_delay)
                    _delay *= backoff
            return None
        return wrapper
    return decorator


# ============================================================
# Data Fetching
# ============================================================

@retry(tries=2, delay=0.5, backoff=2)
def _fetch_one_ticker(ticker):
    """Fetch fundamental data for a single ticker. Returns dict or None."""
    t = yf.Ticker(ticker)
    info = t.info

    # Validate we actually got data
    if not info or "currentPrice" not in info and "previousClose" not in info:
        return None

    mcap = info.get("marketCap")
    # Skip tickers with no market cap (ETFs, weird symbols)
    if mcap is None:
        return None

    price = info.get("currentPrice") or info.get("regularMarketPreviousClose")
    if price is None:
        return None

    # Dividend yield: yfinance returns as percentage (0.36 = 0.36%)
    div_yield = info.get("dividendYield")
    if div_yield is not None:
        div_yield = div_yield / 100.0

    return {
        "ticker": ticker,
        "name": info.get("shortName", ticker)[:30],
        "sector": info.get("sector", "N/D"),
        "industry": info.get("industry", "N/D"),
        "price": price,
        "mcap": mcap,
        # Valuation
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "ev_revenue": info.get("enterpriseToRevenue"),
        "ps": info.get("priceToSales"),
        "peg": info.get("pegRatio"),
        # Profitability
        "roe": info.get("returnOnEquity"),
        "roa": info.get("returnOnAssets"),
        "roce": info.get("returnOnCapitalEmployed"),
        "gross_margins": info.get("grossMargins"),
        "ebitda_margins": info.get("ebitdaMargins"),
        "profit_margins": info.get("profitMargins"),
        # Growth
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "earnings_quarterly_growth": info.get("earningsQuarterlyGrowth"),
        # Financial health
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "total_cash": info.get("totalCash"),
        "total_debt": info.get("totalDebt"),
        "free_cashflow": info.get("freeCashflow"),
        # Dividends
        "dividend_yield": div_yield,
        "payout_ratio": info.get("payoutRatio"),
        # Analyst
        "target_mean": info.get("targetMeanPrice"),
        "recommendation_mean": info.get("recommendationMean"),
        "num_analysts": info.get("numberOfAnalystOpinions"),
        # Risk
        "beta": info.get("beta"),
        "short_pct": info.get("shortPercentOfFloat"),
    }


# ============================================================
# Filters & Presets
# ============================================================

PRESETS = {
    "deep_value": {
        "pe_under": 15,
        "pb_under": 1.5,
        "de_under": 1.0,
        "roe_over": 0.10,
        "description": "Deep Value (estilo Graham): P/E<15, P/B<1.5, D/E<1, ROE>10%",
    },
    "quality": {
        "roe_over": 0.15,
        "gross_margin_over": 0.40,
        "de_under": 1.0,
        "earnings_growth_over": 0.10,
        "description": "Quality: ROE>15%, Margem Bruta>40%, D/E<1, Earnings Growth>10%",
    },
    "growth": {
        "revenue_growth_over": 0.15,
        "earnings_growth_over": 0.20,
        "peg_under": 1.5,
        "description": "Growth: Revenue Growth>15%, Earnings Growth>20%, PEG<1.5",
    },
    "dividend_value": {
        "dividend_over": 0.02,
        "payout_under": 0.60,
        "pe_under": 20,
        "description": "Dividend Value: Yield>2%, Payout<60%, P/E<20",
    },
    "gann": {
        "peg_under": 1.0,
        "roe_over": 0.15,
        "revenue_growth_over": 0.10,
        "description": "GARP (Growth at Reasonable Price): PEG<1, ROE>15%, Revenue Growth>10%",
    },
}


def apply_presets(args):
    """Apply preset values to args if a preset was selected."""
    preset_names = []
    if args.deep_value:
        preset_names.append("deep_value")
    if args.quality:
        preset_names.append("quality")
    if args.growth:
        preset_names.append("growth")
    if args.dividend_value:
        preset_names.append("dividend_value")
    if args.gann:
        preset_names.append("gann")

    for name in preset_names:
        preset = PRESETS[name]
        for key, val in preset.items():
            if key == "description":
                continue
            # Only set if not explicitly overridden by user
            # (args namespace keys use underscores, preset keys too)
            if not hasattr(args, key) or getattr(args, key) is None:
                setattr(args, key, val)
    return preset_names


def _apply_filters(data, args, active_filter_count):
    """Apply fundamental filters to a single ticker's data. Returns result dict or None.

    AND logic: all active filters must pass.
    """
    d = data
    ticker = d["ticker"]
    name = d["name"]

    checks = []

    # --- P/E trailing ---
    if args.pe_under is not None:
        pe = d["pe_trailing"]
        ok = pe is not None and pe > 0 and pe < args.pe_under
        checks.append((True, ok, f"P/E={pe:.1f}" if ok else f"P/E={fmt_num(pe)}"))

    # --- P/E forward ---
    if args.pe_forward_under is not None:
        pef = d["pe_forward"]
        ok = pef is not None and pef > 0 and pef < args.pe_forward_under
        checks.append((True, ok, f"P/E Fwd={pef:.1f}" if ok else f"P/E Fwd={fmt_num(pef)}"))

    # --- P/B ---
    if args.pb_under is not None:
        pb = d["pb"]
        ok = pb is not None and pb > 0 and pb < args.pb_under
        checks.append((True, ok, f"P/B={pb:.2f}" if ok else f"P/B={fmt_num(pb)}"))

    # --- EV/EBITDA ---
    if args.ev_ebitda_under is not None:
        ev = d["ev_ebitda"]
        ok = ev is not None and ev > 0 and ev < args.ev_ebitda_under
        checks.append((True, ok, f"EV/EBITDA={ev:.1f}" if ok else f"EV/EBITDA={fmt_num(ev)}"))

    # --- PEG ---
    if args.peg_under is not None:
        peg = d["peg"]
        ok = peg is not None and peg > 0 and peg < args.peg_under
        checks.append((True, ok, f"PEG={peg:.2f}" if ok else f"PEG={fmt_num(peg)}"))

    # --- ROE ---
    if args.roe_over is not None:
        roe = d["roe"]
        ok = roe is not None and roe > args.roe_over
        checks.append((True, ok, f"ROE={roe*100:.1f}%" if ok else f"ROE={fmt_pct(roe)}"))

    # --- ROA ---
    if args.roa_over is not None:
        roa = d["roa"]
        ok = roa is not None and roa > args.roa_over
        checks.append((True, ok, f"ROA={roa*100:.1f}%" if ok else f"ROA={fmt_pct(roa)}"))

    # --- Gross Margins ---
    if args.gross_margin_over is not None:
        gm = d["gross_margins"]
        ok = gm is not None and gm > args.gross_margin_over
        checks.append((True, ok, f"Gross={gm*100:.1f}%" if ok else f"Gross={fmt_pct(gm)}"))

    # --- Net Margins ---
    if args.net_margin_over is not None:
        nm = d["profit_margins"]
        ok = nm is not None and nm > args.net_margin_over
        checks.append((True, ok, f"Net={nm*100:.1f}%" if ok else f"Net={fmt_pct(nm)}"))

    # --- Revenue Growth ---
    if args.revenue_growth_over is not None:
        rg = d["revenue_growth"]
        ok = rg is not None and rg > args.revenue_growth_over
        checks.append((True, ok, f"Rev={rg*100:.1f}%" if ok else f"Rev={fmt_pct(rg)}"))

    # --- Earnings Growth ---
    if args.earnings_growth_over is not None:
        eg = d["earnings_growth"]
        ok = eg is not None and eg > args.earnings_growth_over
        checks.append((True, ok, f"EPS={eg*100:.1f}%" if ok else f"EPS={fmt_pct(eg)}"))

    # --- D/E ---
    if args.de_under is not None:
        de = d["debt_to_equity"]
        ok = de is not None and de >= 0 and de < args.de_under
        checks.append((True, ok, f"D/E={de:.1f}" if ok else f"D/E={fmt_num(de)}"))

    # --- Current Ratio ---
    if args.current_ratio_over is not None:
        cr = d["current_ratio"]
        ok = cr is not None and cr > args.current_ratio_over
        checks.append((True, ok, f"CR={cr:.2f}" if ok else f"CR={fmt_num(cr)}"))

    # --- Dividend Yield ---
    if args.dividend_over is not None:
        dy = d["dividend_yield"]
        ok = dy is not None and dy > args.dividend_over
        checks.append((True, ok, f"Div={dy*100:.2f}%" if ok else f"Div={fmt_pct(dy)}"))

    # --- Payout Ratio ---
    if args.payout_under is not None:
        po = d["payout_ratio"]
        ok = po is not None and po >= 0 and po < args.payout_under
        checks.append((True, ok, f"Payout={po*100:.0f}%" if ok else f"Payout={fmt_pct(po)}"))

    # --- Beta ---
    if args.beta_under is not None:
        beta = d["beta"]
        ok = beta is not None and beta < args.beta_under
        checks.append((True, ok, f"Beta={beta:.1f}" if ok else f"Beta={fmt_num(beta)}"))

    # --- Market Cap minimum ---
    if args.min_market_cap is not None:
        mcap = d["mcap"]
        ok = mcap is not None and mcap >= args.min_market_cap * 1e9
        checks.append((True, ok, f"Mcap>${args.min_market_cap}B" if ok else f"Mcap={fmt_b(mcap)}"))

    # --- Upside to analyst target ---
    if args.upside_over is not None:
        price = d["price"]
        target = d["target_mean"]
        if price and target and price > 0:
            upside = (target - price) / price
            ok = upside > args.upside_over
            checks.append((True, ok, f"Upside={upside*100:.0f}%" if ok else f"Upside={upside*100:.0f}%"))
        else:
            checks.append((True, False, "Upside=N/D"))

    # --- Evaluation ---
    if args.all:
        include = True
        matched = [c[2] for c in checks if c[0]]
    elif active_filter_count > 0:
        active_checks = [c for c in checks if c[0]]
        if active_checks and all(c[1] for c in active_checks):
            include = True
            matched = [c[2] for c in active_checks]
        else:
            include = False
            matched = []
    else:
        include = False
        matched = []

    if include:
        return {
            "Ticker": ticker,
            "Nome": name,
            "Setor": d["sector"][:20] if d["sector"] else "N/D",
            "Preco": f"${d['price']:.2f}",
            "M Cap": fmt_b(d["mcap"]),
            "P/E": fmt_num(d["pe_trailing"], 1),
            "P/B": fmt_num(d["pb"], 2),
            "ROE": fmt_pct(d["roe"]),
            "Rev Gr": fmt_pct(d["revenue_growth"]),
            "EPS Gr": fmt_pct(d["earnings_growth"]),
            "D/E": fmt_num(d["debt_to_equity"], 1),
            "Div": fmt_pct(d["dividend_yield"]),
            "Sinais": ", ".join(matched) if matched else "—",
        }
    return None


# ============================================================
# Parallel Screening
# ============================================================

def screen_tickers(tickers, args, active_filter_count):
    """Fetch fundamentals in parallel and apply filters."""
    results = []
    total = len(tickers)
    max_workers = min(10, total)  # Slightly fewer workers for fundamental data
    print(f"A analisar {total} tickers ({max_workers} workers)...")

    fetched = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {executor.submit(_fetch_one_ticker, t): t for t in tickers}
        completed = 0
        for future in as_completed(future_to_ticker):
            completed += 1
            if completed % 100 == 0:
                print(f"  {completed}/{total} ({completed*100/total:.0f}%)")
            try:
                data = future.result()
                if data:
                    fetched.append(data)
            except Exception:
                continue

    print(f"  {len(fetched)}/{total} tickers com dados. A aplicar filtros...")

    for data in fetched:
        result = _apply_filters(data, args, active_filter_count)
        if result:
            results.append(result)

    return results


def save_results(results, args, preset_names):
    """Save results to a markdown report."""
    ensure_dirs()
    from datetime import datetime
    from config import get_report_path

    date_str = datetime.now().strftime("%Y-%m-%d")
    path = Path(__file__).parent.parent / "reports" / date_str / "value_screener.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"# Value Screener — {date_str}")
    lines.append("")

    # Describe filters
    if preset_names:
        lines.append("## Presets aplicados")
        for name in preset_names:
            lines.append(f"- **{name}**: {PRESETS[name]['description']}")
        lines.append("")

    filters_desc = []
    if args.pe_under is not None:
        filters_desc.append(f"P/E < {args.pe_under}")
    if args.pe_forward_under is not None:
        filters_desc.append(f"P/E Fwd < {args.pe_forward_under}")
    if args.pb_under is not None:
        filters_desc.append(f"P/B < {args.pb_under}")
    if args.ev_ebitda_under is not None:
        filters_desc.append(f"EV/EBITDA < {args.ev_ebitda_under}")
    if args.peg_under is not None:
        filters_desc.append(f"PEG < {args.peg_under}")
    if args.roe_over is not None:
        filters_desc.append(f"ROE > {args.roe_over*100:.0f}%")
    if args.roa_over is not None:
        filters_desc.append(f"ROA > {args.roa_over*100:.0f}%")
    if args.gross_margin_over is not None:
        filters_desc.append(f"Gross Margin > {args.gross_margin_over*100:.0f}%")
    if args.net_margin_over is not None:
        filters_desc.append(f"Net Margin > {args.net_margin_over*100:.0f}%")
    if args.revenue_growth_over is not None:
        filters_desc.append(f"Revenue Growth > {args.revenue_growth_over*100:.0f}%")
    if args.earnings_growth_over is not None:
        filters_desc.append(f"Earnings Growth > {args.earnings_growth_over*100:.0f}%")
    if args.de_under is not None:
        filters_desc.append(f"D/E < {args.de_under}")
    if args.current_ratio_over is not None:
        filters_desc.append(f"Current Ratio > {args.current_ratio_over}")
    if args.dividend_over is not None:
        filters_desc.append(f"Dividend Yield > {args.dividend_over*100:.1f}%")
    if args.payout_under is not None:
        filters_desc.append(f"Payout Ratio < {args.payout_under*100:.0f}%")
    if args.beta_under is not None:
        filters_desc.append(f"Beta < {args.beta_under}")
    if args.min_market_cap is not None:
        filters_desc.append(f"Market Cap > ${args.min_market_cap}B")
    if args.upside_over is not None:
        filters_desc.append(f"Upside to Target > {args.upside_over*100:.0f}%")

    if filters_desc:
        lines.append("## Filtros ativos")
        lines.append(", ".join(filters_desc))
        lines.append("")

    lines.append(f"## Resultados ({len(results)} encontrados)")
    lines.append("")
    lines.append(tabulate(results, headers="keys", tablefmt="github", showindex=False))
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nResultados guardados: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Value Screener — screening por criterios fundamentais",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python value_screener.py --deep-value
  python value_screener.py --quality
  python value_screener.py --growth
  python value_screener.py --dividend-value
  python value_screener.py --pe-under 15 --roe-over 20 --de-under 0.5
  python value_screener.py --universe nasdaq100 --gann
  python value_screener.py --universe "AAPL,MSFT,NVDA,TSLA" --all

Presets (combinam varios filtros):
  --deep-value       P/E<15, P/B<1.5, D/E<1, ROE>10%
  --quality          ROE>15%, Margem Bruta>40%, D/E<1, Earnings Growth>10%
  --growth           Revenue Growth>15%, Earnings Growth>20%, PEG<1.5
  --dividend-value   Div Yield>2%, Payout<60%, P/E<20
  --gann             PEG<1, ROE>15%, Revenue Growth>10% (GARP)
        """
    )
    parser.add_argument("--universe", "-u", default=DEFAULT_SCREENER_UNIVERSE,
                       help="Universo: 'sp500', 'nasdaq100', 'eurostoxx50', ou tickers separados por virgula")

    # Presets
    parser.add_argument("--deep-value", action="store_true", help="Deep Value (Graham)")
    parser.add_argument("--quality", action="store_true", help="Quality companies")
    parser.add_argument("--growth", action="store_true", help="Growth companies")
    parser.add_argument("--dividend-value", action="store_true", help="Dividend value")
    parser.add_argument("--gann", action="store_true", help="GARP — Growth at Reasonable Price")

    # Valuation filters
    parser.add_argument("--pe-under", type=float, help="P/E trailing abaixo de N")
    parser.add_argument("--pe-forward-under", type=float, help="P/E forward abaixo de N")
    parser.add_argument("--pb-under", type=float, help="P/B abaixo de N")
    parser.add_argument("--ev-ebitda-under", type=float, help="EV/EBITDA abaixo de N")
    parser.add_argument("--peg-under", type=float, help="PEG ratio abaixo de N")

    # Profitability filters
    parser.add_argument("--roe-over", type=float, help="ROE acima de N (ex: 0.20 = 20%%)")
    parser.add_argument("--roa-over", type=float, help="ROA acima de N")
    parser.add_argument("--gross-margin-over", type=float, help="Margem bruta acima de N (ex: 0.40 = 40%%)")
    parser.add_argument("--net-margin-over", type=float, help="Margem liquida acima de N")

    # Growth filters
    parser.add_argument("--revenue-growth-over", type=float, help="Crescimento de receita acima de N")
    parser.add_argument("--earnings-growth-over", type=float, help="Crescimento de earnings acima de N")

    # Financial health filters
    parser.add_argument("--de-under", type=float, help="Debt/Equity abaixo de N")
    parser.add_argument("--current-ratio-over", type=float, help="Current Ratio acima de N")

    # Income filters
    parser.add_argument("--dividend-over", type=float, help="Dividend yield acima de N (ex: 0.02 = 2%%)")
    parser.add_argument("--payout-under", type=float, help="Payout ratio abaixo de N (ex: 0.60 = 60%%)")

    # Risk / Other
    parser.add_argument("--beta-under", type=float, help="Beta abaixo de N")
    parser.add_argument("--min-market-cap", type=float, help="Market Cap minimo em B$ (ex: --min-market-cap 10)")
    parser.add_argument("--upside-over", type=float, help="Upside minimo para analyst target (ex: 0.15 = 15%%)")

    # Output
    parser.add_argument("--all", action="store_true", help="Mostrar todos os tickers (com metricas)")
    parser.add_argument("--top", type=int, default=30, help="Numero maximo de resultados")
    parser.add_argument("--save", action="store_true", default=True, help="Guardar resultado em ficheiro")
    parser.add_argument("--no-save", action="store_true", help="Nao guardar em ficheiro")

    args = parser.parse_args()

    # --- Apply presets ---
    preset_names = apply_presets(args)

    # Count active filters (excluding presets count)
    filter_args = [
        args.pe_under, args.pe_forward_under, args.pb_under, args.ev_ebitda_under,
        args.peg_under, args.roe_over, args.roa_over, args.gross_margin_over,
        args.net_margin_over, args.revenue_growth_over, args.earnings_growth_over,
        args.de_under, args.current_ratio_over, args.dividend_over, args.payout_under,
        args.beta_under, args.min_market_cap, args.upside_over,
    ]
    active_filter_count = sum(1 for f in filter_args if f is not None)

    if active_filter_count == 0 and not args.all:
        print("Erro: especifica pelo menos um filtro ou --all.")
        print("Exemplos: --deep-value, --quality, --pe-under 15, --all")
        print("Usa --help para ver todos os filtros.")
        sys.exit(1)

    # --- Build description ---
    desc_parts = []
    if preset_names:
        desc_parts.append("Presets: " + ", ".join(preset_names))
    else:
        desc_parts.append(f"{active_filter_count} filtro(s) ativo(s)")
    print(f"Universo: {args.universe}")
    print(f"{', '.join(desc_parts)}")

    # --- Get universe ---
    tickers = get_universe(args.universe)
    if not tickers:
        print("Universo vazio ou erro ao carregar.")
        sys.exit(1)

    print(f"\n{tickers} tickers no universo.\n")

    # --- Screen ---
    results = screen_tickers(tickers, args, active_filter_count)

    # --- Display ---
    print(f"\nResultados: {len(results)} encontrados.", end="")
    if len(results) > args.top:
        print(f" Top {args.top}:")
    else:
        print()

    display = results[:args.top] if args.top > 0 else results

    if display:
        print(tabulate(display, headers="keys", tablefmt="github", showindex=False))
    else:
        print("Nenhum ticker encontrado com estes criterios.")

    # --- Save ---
    if args.save and not args.no_save and results:
        save_results(results, args, preset_names)


if __name__ == "__main__":
    main()
