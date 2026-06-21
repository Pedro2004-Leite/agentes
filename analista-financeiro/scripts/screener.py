"""
Screener de stocks por criterios tecnicos.
Uso:
  python screener.py --rsi-oversold --volume-spike
  python screener.py --macd-bullish --adx-trend
  python screener.py --bollinger-squeeze
  python screener.py --new-highs
  python screener.py --universe sp500 --rsi-oversold --top 30
  python screener.py --universe "AAPL,MSFT,NVDA" --all
"""
import sys
import time
from pathlib import Path
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps

sys.path.insert(0, str(Path(__file__).parent))

# Fix Unicode emoji crash on Windows cp1252 terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import DEFAULT_SCREENER_UNIVERSE, ensure_dirs, get_screener_path

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
    print("  pip install yfinance pandas numpy tabulate")
    sys.exit(1)


# ============================================================
# Universes
# ============================================================

def _fetch_wiki_table(url):
    """Fetch Wikipedia table with proper User-Agent (avoids 403)."""
    import urllib.request, io
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        return pd.read_html(io.StringIO(html))


def get_sp500_tickers():
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = _fetch_wiki_table(url)
        df = tables[0]
        tickers = df["Symbol"].tolist()
        return [t.replace(".", "-") for t in tickers]
    except Exception as e:
        print(f"Erro S&P 500: {e}")
        return []


def get_nasdaq100_tickers():
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = _fetch_wiki_table(url)
        for table in tables:
            for col_name in table.columns:
                if col_name.lower() in ("ticker", "symbol"):
                    tickers = table[col_name].tolist()
                    return [t.replace(".", "-") for t in tickers]
        return []
    except Exception as e:
        print(f"Erro NASDAQ 100: {e}")
        return []


def get_eurostoxx50_tickers():
    """Euro Stoxx 50 via Wikipedia (componentes principais)."""
    try:
        url = "https://en.wikipedia.org/wiki/EURO_STOXX_50"
        tables = _fetch_wiki_table(url)
        for table in tables:
            ticker_col = None
            for c in table.columns:
                if c.lower() in ("ticker", "symbol"):
                    ticker_col = c
                    break
            if ticker_col:
                tickers = table[ticker_col].tolist()
                return [t.replace(".", "-") for t in tickers if isinstance(t, str)]
        return []
    except Exception:
        return []


def get_universe(universe_str):
    """Resolver o universo de tickers."""
    if universe_str == "sp500":
        return get_sp500_tickers()
    elif universe_str == "nasdaq100":
        return get_nasdaq100_tickers()
    elif universe_str == "eurostoxx50":
        tickers = get_eurostoxx50_tickers()
        if not tickers:
            print("Euro Stoxx 50 indisponivel. Usa uma lista manual.")
        return tickers
    else:
        return [t.strip().upper() for t in universe_str.split(",") if t.strip()]


# ============================================================
# Indicators
# ============================================================

def compute_indicators(hist):
    """Calcular todos os indicadores tecnicos para uma serie historica."""
    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]
    volume = hist["Volume"]

    indicators = {}

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    indicators["rsi"] = 100 - (100 / (1 + rs))

    # ATR
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    indicators["atr"] = true_range.rolling(14).mean()
    indicators["atr_pct"] = (indicators["atr"] / close) * 100

    # ADX
    plus_dm = high.diff().where(high.diff() > low.diff().abs(), 0)
    minus_dm = low.diff().abs().where(low.diff().abs() > high.diff(), 0)
    atr_adx = true_range.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_adx)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_adx)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    indicators["adx"] = dx.rolling(14).mean()
    indicators["plus_di"] = plus_di
    indicators["minus_di"] = minus_di

    # MACD
    ema_12 = close.ewm(span=12).mean()
    ema_26 = close.ewm(span=26).mean()
    indicators["macd"] = ema_12 - ema_26
    indicators["macd_signal"] = indicators["macd"].ewm(span=9).mean()

    # SMAs
    for p in [20, 50, 200]:
        if len(close) >= p:
            indicators[f"sma_{p}"] = close.rolling(p).mean()

    # Bollinger
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    indicators["bb_upper"] = bb_mid + 2 * bb_std
    indicators["bb_lower"] = bb_mid - 2 * bb_std
    indicators["bb_width"] = ((indicators["bb_upper"] - indicators["bb_lower"]) / bb_mid) * 100

    # Volume ratio
    avg_vol_20 = volume.iloc[-21:-1].mean() if len(volume) >= 21 else volume.mean()
    recent_vol = volume.iloc[-3:].mean()
    indicators["vol_ratio"] = recent_vol / avg_vol_20 if avg_vol_20 > 0 else 1

    # Novos maximos/minimos (50 dias)
    max_50 = high.iloc[-50:].max()
    min_50 = low.iloc[-50:].min()
    current = close.iloc[-1]
    indicators["near_52w_high"] = current >= high.iloc[-252:].max() * 0.98 if len(close) >= 252 else False
    indicators["near_50d_high"] = current >= max_50 * 0.99
    indicators["near_50d_low"] = current <= min_50 * 1.01

    # Momentums
    for label, days in [("1w", 5), ("1m", 21), ("3m", 63)]:
        if len(close) > days:
            indicators[f"perf_{label}"] = ((current - close.iloc[-days]) / close.iloc[-days]) * 100

    return indicators


# ============================================================
# Screening
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


@retry(tries=2, delay=0.5, backoff=2)
def _fetch_one_ticker(ticker):
    """Fetch and process a single ticker. Returns dict or None."""
    t = yf.Ticker(ticker)
    hist = t.history(period="1y")
    if hist.empty or len(hist) < 60:
        return None

    ind = compute_indicators(hist)
    close = hist["Close"]
    current_price = close.iloc[-1]
    name = t.info.get("shortName", ticker)
    mcap = t.info.get("marketCap")

    return {
        "ticker": ticker,
        "name": name,
        "price": current_price,
        "mcap": mcap,
        "indicators": ind,
        "short_pct": t.info.get("shortPercentOfFloat"),
        "short_ratio": t.info.get("shortRatio"),
    }


def _apply_filters(data, args):
    """Apply filters to a single ticker's data. Returns result dict or None.

    Todos os filtros especificados devem passar (AND logic).
    """
    ticker = data["ticker"]
    name = data["name"]
    current_price = data["price"]
    mcap = data["mcap"]
    ind = data["indicators"]

    checks = []  # Lista de (filtro_ativo, passou, label)

    if args.rsi_oversold:
        rsi_val = ind["rsi"].iloc[-1]
        checks.append((True, rsi_val < 30, f"RSI={rsi_val:.0f}"))

    if args.rsi_overbought:
        rsi_val = ind["rsi"].iloc[-1]
        checks.append((True, rsi_val > 70, f"RSI={rsi_val:.0f}"))

    if args.macd_bullish:
        macd_c = ind["macd"].iloc[-1]
        sig_c = ind["macd_signal"].iloc[-1]
        cross = ind["macd"].iloc[-2] <= ind["macd_signal"].iloc[-2] and macd_c > sig_c
        checks.append((True, cross, "MACD bullish cross"))

    if args.macd_bearish:
        macd_c = ind["macd"].iloc[-1]
        sig_c = ind["macd_signal"].iloc[-1]
        cross = ind["macd"].iloc[-2] >= ind["macd_signal"].iloc[-2] and macd_c < sig_c
        checks.append((True, cross, "MACD bearish cross"))

    if args.volume_spike:
        checks.append((True, ind["vol_ratio"] > 2.0, f"Vol={ind['vol_ratio']:.1f}x"))

    if args.adx_trend:
        adx_ok = ind["adx"].iloc[-1] > 25
        direction = "+DI" if ind["plus_di"].iloc[-1] > ind["minus_di"].iloc[-1] else "-DI"
        checks.append((True, adx_ok, f"ADX={ind['adx'].iloc[-1]:.0f}({direction})"))

    if args.bollinger_squeeze:
        checks.append((True, ind["bb_width"].iloc[-1] < 5, "BB squeeze"))

    if args.above_sma200:
        ok = "sma_200" in ind and current_price > ind["sma_200"].iloc[-1]
        checks.append((True, ok, "↑SMA200"))

    if args.below_sma200:
        ok = "sma_200" in ind and current_price < ind["sma_200"].iloc[-1]
        checks.append((True, ok, "↓SMA200"))

    if args.new_highs:
        checks.append((True, ind.get("near_50d_high", False), "Novo max 50d"))

    if args.new_lows:
        checks.append((True, ind.get("near_50d_low", False), "Novo min 50d"))

    if args.momentum_1m:
        checks.append((True, ind.get("perf_1m", 0) > 5, f"1M={ind.get('perf_1m', 0):.1f}%"))

    if args.momentum_neg_1m:
        checks.append((True, ind.get("perf_1m", 0) < -5, f"1M={ind.get('perf_1m', 0):.1f}%"))

    if args.short_squeeze:
        si = data.get("short_pct")
        sr = data.get("short_ratio")
        ok = si is not None and sr is not None and si > 0.15 and sr > 5
        checks.append((True, ok, f"Short{si*100:.0f}%" if ok else "Short✗"))

    # --- Avaliacao: AND logic (todos os filtros ativos devem passar) ---
    active_checks = [c for c in checks if c[0]]  # (ativo, passou, label)
    if args.all:
        include = True
        matched = [c[2] for c in checks if c[0]]
    elif active_checks:
        all_pass = all(c[1] for c in active_checks)
        if all_pass:
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
            "Nome": name[:25] if name else ticker,
            "Preco": f"${current_price:.2f}",
            "RSI": f"{ind['rsi'].iloc[-1]:.0f}",
            "ADX": f"{ind['adx'].iloc[-1]:.0f}" if "adx" in ind else "N/D",
            "Vol": f"{ind['vol_ratio']:.1f}x",
            "ATR%": f"{ind['atr_pct'].iloc[-1]:.1f}%" if "atr_pct" in ind else "N/D",
            "M Cap": f"${mcap/1e9:.1f}B" if mcap and not np.isnan(mcap) else "N/D",
            "Sinais": ", ".join(matched) if matched else "—",
        }
    return None


def screen_tickers(tickers, args):
    """Executar screening em paralelo com ThreadPoolExecutor."""
    results = []
    total = len(tickers)
    max_workers = min(12, total)
    print(f"A analisar {total} tickers ({max_workers} workers)...")

    # Fetch all ticker data in parallel
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

    # Apply filters (fast, single-thread OK)
    for data in fetched:
        result = _apply_filters(data, args)
        if result:
            results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Screener de stocks — filtros tecnicos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python screener.py --rsi-oversold --volume-spike   (bounces com volume)
  python screener.py --macd-bullish --adx-trend       (momentum forte)
  python screener.py --bollinger-squeeze               (breakouts iminentes)
  python screener.py --new-highs --above-sma200        (trend following)
  python screener.py --rsi-overbought                   (procura de shorts)
  python screener.py --momentum-neg-1m --rsi-oversold  (reversao de queda)
        """
    )
    parser.add_argument("--universe", "-u", default=DEFAULT_SCREENER_UNIVERSE,
                       help="Universo: 'sp500', 'nasdaq100', 'eurostoxx50', ou tickers separados por virgula")
    # Filtros
    parser.add_argument("--rsi-oversold", action="store_true", help="RSI < 30")
    parser.add_argument("--rsi-overbought", action="store_true", help="RSI > 70")
    parser.add_argument("--macd-bullish", action="store_true", help="MACD acabou de cruzar acima")
    parser.add_argument("--macd-bearish", action="store_true", help="MACD acabou de cruzar abaixo")
    parser.add_argument("--volume-spike", action="store_true", help="Volume > 2x media")
    parser.add_argument("--adx-trend", action="store_true", help="ADX > 25 (tendencia forte)")
    parser.add_argument("--bollinger-squeeze", action="store_true", help="Bollinger Band Width < 5%%")
    parser.add_argument("--above-sma200", action="store_true", help="Preco acima da SMA 200")
    parser.add_argument("--below-sma200", action="store_true", help="Preco abaixo da SMA 200")
    parser.add_argument("--new-highs", action="store_true", help="Proximo do maximo 50 dias")
    parser.add_argument("--new-lows", action="store_true", help="Proximo do minimo 50 dias")
    parser.add_argument("--momentum-1m", action="store_true", help="Momentum 1 mes > 5%%")
    parser.add_argument("--momentum-neg-1m", action="store_true", help="Momentum 1 mes < -5%%")
    parser.add_argument("--short-squeeze", action="store_true", help="Short interest > 15%% e days-to-cover > 5")
    parser.add_argument("--all", action="store_true", help="Mostrar todos os tickers (com indicadores)")
    # Output
    parser.add_argument("--top", type=int, default=25, help="Numero maximo de resultados")
    parser.add_argument("--save", action="store_true", default=True, help="Guardar resultado em ficheiro")

    args = parser.parse_args()

    filters_active = [
        args.rsi_oversold, args.rsi_overbought,
        args.macd_bullish, args.macd_bearish,
        args.volume_spike, args.adx_trend, args.bollinger_squeeze,
        args.above_sma200, args.below_sma200,
        args.new_highs, args.new_lows,
        args.momentum_1m, args.momentum_neg_1m,
        args.short_squeeze,
        args.all,
    ]

    if not any(filters_active):
        print("Erro: especifica pelo menos um filtro.\n")
        print("Exemplos:")
        print("  python screener.py --rsi-oversold --volume-spike")
        print("  python screener.py --macd-bullish --adx-trend")
        print("  python screener.py --bollinger-squeeze --universe nasdaq100")
        print("  python screener.py --new-highs --above-sma200 --top 15")
        sys.exit(1)

    filter_names = []
    if args.rsi_oversold: filter_names.append("RSI oversold")
    if args.rsi_overbought: filter_names.append("RSI overbought")
    if args.macd_bullish: filter_names.append("MACD bullish cross")
    if args.macd_bearish: filter_names.append("MACD bearish cross")
    if args.volume_spike: filter_names.append("Volume spike >2x")
    if args.adx_trend: filter_names.append("ADX >25 trend")
    if args.bollinger_squeeze: filter_names.append("Bollinger squeeze")
    if args.above_sma200: filter_names.append("Acima SMA200")
    if args.below_sma200: filter_names.append("Abaixo SMA200")
    if args.new_highs: filter_names.append("Novos maximos 50d")
    if args.new_lows: filter_names.append("Novos minimos 50d")
    if args.momentum_1m: filter_names.append("Momentum 1M >5%")
    if args.momentum_neg_1m: filter_names.append("Momentum 1M <-5%")
    if args.all: filter_names.append("All (todos)")
    if args.short_squeeze: filter_names.append("Short squeeze >15%")

    print(f"Universo: {args.universe}")
    print(f"Filtros: {', '.join(filter_names)}")
    print()

    tickers = get_universe(args.universe)
    if not tickers:
        print("Nenhum ticker encontrado.")
        sys.exit(1)

    print(f"{len(tickers)} tickers no universo.\n")

    results = screen_tickers(tickers, args)

    if results:
        df = pd.DataFrame(results)

        # Ordenar inteligentemente
        if args.volume_spike:
            df = df.sort_values("Vol", ascending=False)
        elif args.rsi_oversold:
            df = df.sort_values("RSI", ascending=True)
        elif args.rsi_overbought:
            df = df.sort_values("RSI", ascending=False)
        elif args.new_highs:
            df = df.sort_values("Preco", ascending=False)

        display_df = df.head(args.top)

        print(f"\nResultados: {len(df)} encontrados. Top {min(args.top, len(df))}:")
        print("=" * 100)
        print(tabulate(display_df, headers="keys", tablefmt="pipe", showindex=False))

        # Guardar
        if args.save:
            ensure_dirs()
            date_str = pd.Timestamp.now().strftime("%Y-%m-%d")
            output_path = get_screener_path(date_str)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# Screener Results — {date_str}\n\n")
                f.write(f"**Filtros:** {', '.join(filter_names)}\n")
                f.write(f"**Universo:** {args.universe} ({len(tickers)} tickers)\n")
                f.write(f"**Resultados:** {len(df)}\n\n")
                f.write(tabulate(display_df, headers="keys", tablefmt="pipe", showindex=False))

            print(f"\nResultados guardados: {output_path}")
    else:
        print("Nenhum resultado encontrado com os filtros atuais.")
        print("Tenta filtros mais amplos ou outro universo.")


if __name__ == "__main__":
    main()
