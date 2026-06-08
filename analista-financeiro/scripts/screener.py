"""
Screener de stocks por criterios tecnicos e fundamentais.
Uso:
  python screener.py --rsi-oversold
  python screener.py --rsi-overbought
  python screener.py --macd-bullish
  python screener.py --volume-spike
  python screener.py --universe sp500 --rsi-oversold
  python screener.py --universe "AAPL,MSFT,NVDA,TSLA" --rsi-oversold
"""
import sys
import os
from pathlib import Path
import argparse
import time

sys.path.insert(0, str(Path(__file__).parent))
from config import DEFAULT_SCREENER_UNIVERSE, ensure_dirs

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("Erro: instala as dependencias primeiro")
    print("  pip install yfinance pandas numpy")
    sys.exit(1)


def get_sp500_tickers():
    """Obter lista de tickers do S&P 500 via Wikipedia (gratis)."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        df = tables[0]
        tickers = df["Symbol"].tolist()
        # Limpar tickers com pontos (ex: BRK.B -> BRK-B para yfinance)
        tickers = [t.replace(".", "-") for t in tickers]
        return tickers
    except Exception as e:
        print(f"Erro ao obter S&P 500: {e}")
        print("Usa --universe para especificar tickers manualmente.")
        return []


def get_nasdaq100_tickers():
    """Obter lista do NASDAQ 100 via Wikipedia."""
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = pd.read_html(url)
        # A tabela certa varia, procurar a que tem 'Ticker' ou 'Symbol'
        for table in tables:
            cols = [c.lower() for c in table.columns]
            if "ticker" in cols or "symbol" in cols:
                col = "Ticker" if "Ticker" in table.columns else "Symbol"
                if col in table.columns:
                    tickers = table[col].tolist()
                    return [t.replace(".", "-") for t in tickers]
        return []
    except Exception as e:
        print(f"Erro ao obter NASDAQ 100: {e}")
        return []


def get_universe(universe_str):
    """Resolver o universo de tickers."""
    if universe_str == "sp500":
        return get_sp500_tickers()
    elif universe_str == "nasdaq100":
        return get_nasdaq100_tickers()
    else:
        # Tickers separados por virgula
        return [t.strip().upper() for t in universe_str.split(",")]


def rsi(prices, period=14):
    """Calcular RSI."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def screen_tickers(tickers, args):
    """Executar screening."""
    results = []
    total = len(tickers)
    print(f"A analisar {total} tickers...")

    for i, ticker in enumerate(tickers):
        if i % 50 == 0 and i > 0:
            # Pausa para nao sobrecarregar a API
            print(f"  Progresso: {i}/{total} ({i*100/total:.0f}%)")
            time.sleep(0.5)

        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="6mo")
            if hist.empty or len(hist) < 60:
                continue

            close = hist["Close"]
            volume = hist["Volume"]
            current_price = close.iloc[-1]
            name = t.info.get("shortName", ticker)

            # Calcular indicadores
            rsi_val = rsi(close).iloc[-1]

            # MACD
            ema_12 = close.ewm(span=12).mean()
            ema_26 = close.ewm(span=26).mean()
            macd_line = ema_12 - ema_26
            signal_line = macd_line.ewm(span=9).mean()

            macd_current = macd_line.iloc[-1]
            signal_current = signal_line.iloc[-1]
            macd_prev = macd_line.iloc[-2]
            signal_prev = signal_line.iloc[-2]

            # Volume
            avg_vol = volume.iloc[-21:-1].mean()
            recent_vol = volume.iloc[-3:].mean()
            vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1

            # SMA 20, 50
            sma_20 = close.rolling(20).mean().iloc[-1]
            sma_50 = close.rolling(50).mean().iloc[-1]

            # Filtros
            passed = []
            include = False

            # RSI oversold
            if args.rsi_oversold and rsi_val < 30:
                passed.append(f"RSI={rsi_val:.1f}")
                include = True

            # RSI overbought
            if args.rsi_overbought and rsi_val > 70:
                passed.append(f"RSI={rsi_val:.1f}")
                include = True

            # MACD bullish cross
            if args.macd_bullish:
                if macd_prev <= signal_prev and macd_current > signal_current:
                    passed.append("MACD bullish cross")
                    include = True

            # MACD bearish cross
            if args.macd_bearish:
                if macd_prev >= signal_prev and macd_current < signal_current:
                    passed.append("MACD bearish cross")
                    include = True

            # Volume spike
            if args.volume_spike and vol_ratio > 2.0:
                passed.append(f"Vol={vol_ratio:.1f}x")
                include = True

            # SMA crosses
            if args.sma_cross and current_price > sma_20 and current_price < sma_50:
                # Acima de SMA20 mas abaixo de SMA50 (potencial breakout)
                passed.append("SMA20<Price<SMA50")
                include = True

            if include or args.all:
                results.append({
                    "Ticker": ticker,
                    "Nome": name[:30],
                    "Preco": f"${current_price:.2f}",
                    "RSI": f"{rsi_val:.1f}",
                    "Vol Ratio": f"{vol_ratio:.1f}x",
                    "Sinais": ", ".join(passed),
                })

        except Exception:
            continue

    return results


def main():
    parser = argparse.ArgumentParser(description="Stock Screener")
    parser.add_argument(
        "--universe", "-u",
        default=DEFAULT_SCREENER_UNIVERSE,
        help="Universo de tickers: 'sp500', 'nasdaq100', ou lista separada por virgulas"
    )
    parser.add_argument("--rsi-oversold", action="store_true", help="RSI < 30")
    parser.add_argument("--rsi-overbought", action="store_true", help="RSI > 70")
    parser.add_argument("--macd-bullish", action="store_true", help="MACD cruzou acima do sinal")
    parser.add_argument("--macd-bearish", action="store_true", help="MACD cruzou abaixo do sinal")
    parser.add_argument("--volume-spike", action="store_true", help="Volume 2x acima da media")
    parser.add_argument("--sma-cross", action="store_true", help="Preco entre SMA20 e SMA50")
    parser.add_argument("--all", action="store_true", help="Mostrar todos os tickers com indicadores")
    parser.add_argument("--top", type=int, default=20, help="Numero maximo de resultados")

    args = parser.parse_args()

    # Validar que pelo menos um filtro foi selecionado
    if not any([args.rsi_oversold, args.rsi_overbought, args.macd_bullish,
                args.macd_bearish, args.volume_spike, args.sma_cross, args.all]):
        print("Erro: especifica pelo menos um filtro.")
        print("Exemplo: python screener.py --rsi-oversold --volume-spike")
        print("         python screener.py --macd-bullish --universe AAPL,MSFT,NVDA")
        sys.exit(1)

    print(f"Universo: {args.universe}")
    print(f"Filtros: ", end="")
    filters = []
    if args.rsi_oversold: filters.append("RSI oversold")
    if args.rsi_overbought: filters.append("RSI overbought")
    if args.macd_bullish: filters.append("MACD bullish")
    if args.macd_bearish: filters.append("MACD bearish")
    if args.volume_spike: filters.append("Volume spike")
    if args.sma_cross: filters.append("SMA cross")
    if args.all: filters.append("All tickers")
    print(", ".join(filters))
    print("")

    tickers = get_universe(args.universe)
    if not tickers:
        print("Nenhum ticker encontrado no universo especificado.")
        sys.exit(1)

    print(f"{len(tickers)} tickers carregados.\n")

    results = screen_tickers(tickers, args)

    if results:
        df = pd.DataFrame(results)
        # Ordenar por RSI (oversold primeiro) ou volume (spike primeiro)
        if args.volume_spike:
            df = df.sort_values("Vol Ratio", ascending=False)
        elif args.rsi_oversold:
            df = df.sort_values("RSI", ascending=True)
        elif args.rsi_overbought:
            df = df.sort_values("RSI", ascending=False)

        display_df = df.head(args.top)

        print(f"\nResultados: {len(df)} encontrados. Top {args.top}:")
        print("=" * 90)

        # Formatar como tabela
        from tabulate import tabulate
        print(tabulate(display_df, headers="keys", tablefmt="pipe", showindex=False))

        # Guardar
        ensure_dirs()
        date_str = pd.Timestamp.now().strftime("%Y-%m-%d")
        output_path = Path(__file__).parent.parent / "reports" / date_str / "screener.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# Screener Results — {date_str}\n\n")
            f.write(f"Filtros: {', '.join(filters)}\n")
            f.write(f"Universo: {args.universe} ({len(tickers)} tickers)\n")
            f.write(f"Resultados: {len(df)}\n\n")
            f.write(tabulate(display_df, headers="keys", tablefmt="pipe", showindex=False))

        print(f"\nResultados guardados em: {output_path}")
    else:
        print("Nenhum resultado encontrado com os filtros atuais.")


if __name__ == "__main__":
    main()
