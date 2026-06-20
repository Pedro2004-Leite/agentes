"""
Deteção de padrões de candlestick.
Uso standalone: python patterns.py <TICKER>
Integrado com stock_analysis e screener.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("Erro: pip install yfinance pandas numpy")
    sys.exit(1)


def detect_patterns(df):
    """
    Detecta padroes de candlestick num DataFrame OHLCV.
    Retorna lista de dicts: {pattern, date, direction, strength, description}
    """
    if df.empty or len(df) < 3:
        return []

    open_ = df["Open"]
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    volume = df["Volume"] if "Volume" in df.columns else pd.Series(1, index=df.index)

    body = (close - open_).abs()
    upper_wick = high - close.combine(open_, max)
    lower_wick = close.combine(open_, min) - low
    total_range = high - low
    avg_body = body.rolling(10).mean()

    patterns = []
    idx = len(df) - 1  # Apenas o candle mais recente
    prev = idx - 1
    prev2 = idx - 2

    # ---- Doji ----
    if body.iloc[idx] < total_range.iloc[idx] * 0.1 and total_range.iloc[idx] > 0:
        patterns.append({
            "pattern": "Doji",
            "date": df.index[idx],
            "direction": "neutral",
            "strength": 2,
            "description": "Indecisao — possivel reversão se em suporte/resistencia",
        })

    # ---- Hammer (bullish reversal at bottom) ----
    if (body.iloc[idx] > 0 and total_range.iloc[idx] > 0 and
        lower_wick.iloc[idx] > body.iloc[idx] * 2 and
        upper_wick.iloc[idx] < body.iloc[idx] * 0.5):
        # Context: was price declining?
        if close.iloc[prev] < close.iloc[prev-2]:
            patterns.append({
                "pattern": "Hammer (Bullish)",
                "date": df.index[idx],
                "direction": "bullish",
                "strength": 3,
                "description": "Fundo com rejeição — possivel reversal bullish",
            })

    # ---- Shooting Star (bearish reversal at top) ----
    if (body.iloc[idx] > 0 and total_range.iloc[idx] > 0 and
        upper_wick.iloc[idx] > body.iloc[idx] * 2 and
        lower_wick.iloc[idx] < body.iloc[idx] * 0.5):
        if close.iloc[prev] > close.iloc[prev-2]:
            patterns.append({
                "pattern": "Shooting Star (Bearish)",
                "date": df.index[idx],
                "direction": "bearish",
                "strength": 3,
                "description": "Topo com rejeição — possivel reversal bearish",
            })

    # ---- Bullish Engulfing ----
    if (close.iloc[idx] > open_.iloc[idx] and
        close.iloc[prev] < open_.iloc[prev] and
        open_.iloc[idx] < close.iloc[prev] and
        close.iloc[idx] > open_.iloc[prev] and
        body.iloc[idx] > avg_body.iloc[idx] * 1.5):
        patterns.append({
            "pattern": "Bullish Engulfing",
            "date": df.index[idx],
            "direction": "bullish",
            "strength": 4,
            "description": "Compradores tomaram controlo — forte sinal bullish",
        })

    # ---- Bearish Engulfing ----
    if (close.iloc[idx] < open_.iloc[idx] and
        close.iloc[prev] > open_.iloc[prev] and
        open_.iloc[idx] > close.iloc[prev] and
        close.iloc[idx] < open_.iloc[prev] and
        body.iloc[idx] > avg_body.iloc[idx] * 1.5):
        patterns.append({
            "pattern": "Bearish Engulfing",
            "date": df.index[idx],
            "direction": "bearish",
            "strength": 4,
            "description": "Vendedores tomaram controlo — forte sinal bearish",
        })

    # ---- Inside Bar ----
    if (high.iloc[idx] < high.iloc[prev] and
        low.iloc[idx] > low.iloc[prev]):
        patterns.append({
            "pattern": "Inside Bar",
            "date": df.index[idx],
            "direction": "neutral",
            "strength": 1,
            "description": "Consolidacao — breakout do range do dia anterior define direcao",
        })

    # ---- Morning Star (3-candle bullish reversal) ----
    if prev2 >= 0:
        # Day 1: long red candle
        day1_red = close.iloc[prev2] < open_.iloc[prev2] and body.iloc[prev2] > avg_body.iloc[prev2]
        # Day 2: small body (indecision)
        day2_small = body.iloc[prev] < avg_body.iloc[prev] * 0.5
        # Day 3: long green candle closing above day1 midpoint
        day3_green = (close.iloc[idx] > open_.iloc[idx] and
                      body.iloc[idx] > avg_body.iloc[idx] and
                      close.iloc[idx] > (close.iloc[prev2] + open_.iloc[prev2]) / 2)

        if day1_red and day2_small and day3_green:
            patterns.append({
                "pattern": "Morning Star (Bullish)",
                "date": df.index[idx],
                "direction": "bullish",
                "strength": 5,
                "description": "Reversao de 3 velas — sinal bullish forte",
            })

    # ---- Evening Star (3-candle bearish reversal) ----
    if prev2 >= 0:
        day1_green = close.iloc[prev2] > open_.iloc[prev2] and body.iloc[prev2] > avg_body.iloc[prev2]
        day2_small = body.iloc[prev] < avg_body.iloc[prev] * 0.5
        day3_red = (close.iloc[idx] < open_.iloc[idx] and
                    body.iloc[idx] > avg_body.iloc[idx] and
                    close.iloc[idx] < (close.iloc[prev2] + open_.iloc[prev2]) / 2)

        if day1_green and day2_small and day3_red:
            patterns.append({
                "pattern": "Evening Star (Bearish)",
                "date": df.index[idx],
                "direction": "bearish",
                "strength": 5,
                "description": "Reversao de 3 velas — sinal bearish forte",
            })

    # ---- Gap Detection ----
    if prev >= 0:
        gap_pct = (open_.iloc[idx] - close.iloc[prev]) / close.iloc[prev] * 100
        if gap_pct > 2:
            patterns.append({
                "pattern": f"Gap Up ({gap_pct:.1f}%)",
                "date": df.index[idx],
                "direction": "bullish",
                "strength": 3,
                "description": "Gap significativo — atencao a gap fill ou continuacao",
            })
        elif gap_pct < -2:
            patterns.append({
                "pattern": f"Gap Down ({gap_pct:.1f}%)",
                "date": df.index[idx],
                "direction": "bearish",
                "strength": 3,
                "description": "Gap negativo significativo — atencao a gap fill ou continuacao",
            })

    return patterns


def analyze_ticker(ticker, days=60):
    """Analisar padroes num ticker nos ultimos N dias."""
    t = yf.Ticker(ticker)
    hist = t.history(period=f"{min(days*2, 252)}d")
    if hist.empty:
        return [], hist

    recent = hist.iloc[-days:]
    patterns = detect_patterns(recent)
    return patterns, recent


def print_patterns(ticker, patterns, current_price=None):
    """Print patterns para o terminal."""
    name = ticker.upper()
    print(f"\n{'='*60}")
    print(f"  Padrões de Candlestick: {name}")
    if current_price:
        print(f"  Preço atual: ${current_price:.2f}")
    print(f"{'='*60}")

    if not patterns:
        print("  Nenhum padrão detectado nos candles recentes.")
        return

    for p in patterns:
        emoji = "🟢" if p["direction"] == "bullish" else "🔴" if p["direction"] == "bearish" else "⚪"
        strength_bars = "█" * p["strength"] + "░" * (5 - p["strength"])
        date_str = p["date"].strftime("%d/%m/%Y") if hasattr(p["date"], "strftime") else str(p["date"])
        print(f"\n  {emoji} {p['pattern']}")
        print(f"  Data: {date_str} | Força: [{strength_bars}] {p['strength']}/5")
        print(f"  {p['description']}")

    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Detecao de padroes de candlestick")
    parser.add_argument("ticker", help="Ticker a analisar")
    parser.add_argument("--days", type=int, default=5, help="Ver ultimos N candles (default: 5)")
    parser.add_argument("--all", action="store_true", help="Mostrar todos os candles com indicadores")
    args = parser.parse_args()

    ticker = args.ticker.strip().upper()
    t = yf.Ticker(ticker)
    hist = t.history(period="3mo")

    if hist.empty:
        print(f"Sem dados para {ticker}")
        sys.exit(1)

    price = hist["Close"].iloc[-1]
    recent = hist.iloc[-args.days:]
    patterns = detect_patterns(recent)

    print(f"\n{ticker} — ultimos {args.days} candles:")
    if args.all:
        print(t.recent[["Open", "High", "Low", "Close", "Volume"]].to_string())

    print_patterns(ticker, patterns, price)


if __name__ == "__main__":
    main()
