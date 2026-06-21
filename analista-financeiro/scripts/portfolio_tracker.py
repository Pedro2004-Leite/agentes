"""
Portfolio tracker — tracking de posicoes abertas, P&L, metricas de risco.
Uso:
  python portfolio_tracker.py                     (ver portfolio atual)
  python portfolio_tracker.py --add AAPL 10 150.00 --stop 140.00 --target 170.00
  python portfolio_tracker.py --close AAPL 165.00
  python portfolio_tracker.py --update AAPL --stop 148.00
  python portfolio_tracker.py --risk              (analise de risco avancada)
  python portfolio_tracker.py --size AAPL 150.00 140.00   (calcula position size)
  python portfolio_tracker.py --clean
Ficheiro de posicoes: ../positions.json
"""
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Fix Unicode emoji crash on Windows cp1252 terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import POSITIONS_FILE, REPORTS_DIR, ensure_dirs

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
# Portfolio data
# ============================================================

def load_positions():
    """Carregar posicoes do ficheiro JSON."""
    if not POSITIONS_FILE.exists():
        return []
    with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_positions(positions):
    """Guardar posicoes no ficheiro JSON."""
    ensure_dirs()
    POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(positions, f, indent=2, ensure_ascii=False, default=str)


def get_current_prices(tickers):
    """Obter precos atuais para uma lista de tickers."""
    prices = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            price = t.info.get("currentPrice") or t.info.get("regularMarketPreviousClose")
            name = t.info.get("shortName", ticker)
            if price:
                prices[ticker] = {"price": price, "name": name}
        except Exception:
            pass
    return prices


# ============================================================
# Commands
# ============================================================

def cmd_show():
    """Mostrar portfolio atual com P&L."""
    positions = load_positions()
    if not positions:
        print("Portfolio vazio. Usa --add para adicionar posicoes.")
        return

    # Obter precos atuais
    tickers = [p["ticker"] for p in positions if p["status"] == "open"]
    prices = get_current_prices(tickers)

    rows = []
    total_invested = 0
    total_current = 0
    total_pnl = 0

    for p in positions:
        ticker = p["ticker"]
        status = p["status"]
        entry = p["entry_price"]
        shares = p["shares"]
        stop = p.get("stop_loss")
        target = p.get("take_profit")

        current_data = prices.get(ticker, {})
        current_price = current_data.get("price")
        name = current_data.get("name", ticker)

        if status == "closed":
            exit_price = p.get("exit_price", entry)
            pnl = (exit_price - entry) * shares
            pnl_pct = ((exit_price - entry) / entry) * 100
            rows.append({
                "Ticker": ticker,
                "Nome": name[:20],
                "Status": "FECHADA",
                "Entrada": f"${entry:.2f}",
                "Saida": f"${exit_price:.2f}",
                "Preco Atual": "—",
                "Shares": shares,
                "P&L": f"${pnl:.2f}",
                "P&L %": f"{pnl_pct:+.1f}%",
                "Stop": "—",
                "Target": "—",
            })
        elif current_price:
            invested = entry * shares
            current_value = current_price * shares
            pnl = current_value - invested
            pnl_pct = ((current_price - entry) / entry) * 100

            total_invested += invested
            total_current += current_value
            total_pnl += pnl

            # Sinais
            signals = []
            if stop and current_price <= stop:
                signals.append("⛔ STOP HIT")
            if target and current_price >= target:
                signals.append("✅ TARGET HIT")

            rows.append({
                "Ticker": ticker,
                "Nome": name[:20],
                "Status": "OPEN" if not signals else "ALERT",
                "Entrada": f"${entry:.2f}",
                "Saida": "—",
                "Preco Atual": f"${current_price:.2f}",
                "Shares": shares,
                "P&L": f"${pnl:.2f}",
                "P&L %": f"{pnl_pct:+.1f}%",
                "Stop": f"${stop:.2f}" if stop else "—",
                "Target": f"${target:.2f}" if target else "—",
                "Alertas": " ".join(signals) if signals else "—",
            })
        else:
            rows.append({
                "Ticker": ticker,
                "Nome": name[:20],
                "Status": "OPEN (sem preco)",
                "Entrada": f"${entry:.2f}",
                "Saida": "—",
                "Preco Atual": "N/D",
                "Shares": shares,
                "P&L": "N/D",
                "P&L %": "N/D",
                "Stop": f"${stop:.2f}" if stop else "—",
                "Target": f"${target:.2f}" if target else "—",
                "Alertas": "—",
            })

    print()
    print("=" * 100)
    print("  PORTFOLIO TRACKER")
    print("=" * 100)
    print()
    print(tabulate(rows, headers="keys", tablefmt="pipe", showindex=False))
    print()

    if total_invested > 0:
        print(f"Capital investido: ${total_invested:,.2f}")
        print(f"Valor atual: ${total_current:,.2f}")
        print(f"P&L total: ${total_pnl:,.2f} ({(total_pnl/total_invested)*100:+.1f}%)")
        print()

        # Open positions only
        open_pos = [p for p in positions if p["status"] == "open"]
        if open_pos and prices:
            print(f"Posicoes abertas: {len(open_pos)}")
            # Rácio win/loss
            winning = sum(1 for p in positions if p["status"] == "closed" and p.get("exit_price", 0) > p["entry_price"])
            losing = sum(1 for p in positions if p["status"] == "closed" and p.get("exit_price", 0) <= p["entry_price"])
            closed = winning + losing
            if closed > 0:
                print(f"Win rate (posicoes fechadas): {winning}/{closed} = {winning/closed*100:.0f}%")
            print()

            # Alertas
            tickers_raw = [p["ticker"] for p in open_pos]
            print("Live alerts:")
            for i, p in enumerate(open_pos):
                ticker = p["ticker"]
                if ticker in prices:
                    cp = prices[ticker]["price"]
                    entry = p["entry_price"]
                    pnl = ((cp - entry) / entry) * 100
                    status = "🟢" if pnl > 0 else "🔴"
                    msg = f"  {status} {ticker}: {pnl:+.1f}% (${cp:.2f})"
                    if p.get("stop_loss") and cp <= p["stop_loss"]:
                        msg += " ⛔ STOP!"
                    if p.get("take_profit") and cp >= p["take_profit"]:
                        msg += " ✅ TARGET!"
                    print(msg)
    print()


def cmd_add(ticker, shares, entry, stop=None, target=None, note=""):
    """Adicionar nova posicao."""
    positions = load_positions()

    # Verificar se ja existe aberta
    for p in positions:
        if p["ticker"].upper() == ticker.upper() and p["status"] == "open":
            print(f"Ja tens uma posicao aberta em {ticker.upper()}.")
            print(f"  {p['shares']} shares @ ${p['entry_price']:.2f}")
            return

    # Validar stop/target
    if stop and stop >= entry:
        print(f"Aviso: stop (${stop:.2f}) esta acima do entry (${entry:.2f}). Ajusta.")
    if target and target <= entry:
        print(f"Aviso: target (${target:.2f}) esta abaixo do entry (${entry:.2f}). Ajusta.")

    position = {
        "ticker": ticker.upper(),
        "shares": shares,
        "entry_price": entry,
        "stop_loss": stop,
        "take_profit": target,
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
        "note": note,
        "status": "open",
        "exit_price": None,
        "exit_date": None,
    }
    positions.append(position)
    save_positions(positions)

    invested = entry * shares
    risk = (entry - stop) * shares if stop else 0
    reward = (target - entry) * shares if target else 0
    rr = reward / risk if risk > 0 else 0

    print(f"\nPosicao adicionada: {ticker.upper()}")
    print(f"  {shares} shares @ ${entry:.2f} = ${invested:,.2f} investido")
    if stop:
        print(f"  Stop: ${stop:.2f} (risco: ${risk:.2f})")
    if target:
        print(f"  Target: ${target:.2f} (reward: ${reward:.2f})")
    if risk and reward:
        print(f"  R/R: 1:{rr:.1f}")
    print()


def cmd_close(ticker, exit_price, exit_date=None):
    """Fechar uma posicao."""
    positions = load_positions()
    updated = False

    for p in positions:
        if p["ticker"].upper() == ticker.upper() and p["status"] == "open":
            p["status"] = "closed"
            p["exit_price"] = exit_price
            p["exit_date"] = exit_date or datetime.now().strftime("%Y-%m-%d")
            pnl = (exit_price - p["entry_price"]) * p["shares"]
            pnl_pct = ((exit_price - p["entry_price"]) / p["entry_price"]) * 100
            print(f"\n{ticker.upper()} fechada:")
            print(f"  Entrada: ${p['entry_price']:.2f} → Saida: ${exit_price:.2f}")
            print(f"  P&L: ${pnl:.2f} ({pnl_pct:+.1f}%)")
            print(f"  Hold: {p['entry_date']} → {p['exit_date']}")
            updated = True
            break

    if not updated:
        print(f"Posicao aberta em {ticker.upper()} nao encontrada.")
        return

    save_positions(positions)
    print()


def cmd_update(ticker, stop=None, target=None, note=None):
    """Atualizar stop, target ou nota de uma posicao."""
    positions = load_positions()

    for p in positions:
        if p["ticker"].upper() == ticker.upper() and p["status"] == "open":
            if stop is not None:
                p["stop_loss"] = stop
                print(f"Stop atualizado: {ticker.upper()} → ${stop:.2f}")
            if target is not None:
                p["take_profit"] = target
                print(f"Target atualizado: {ticker.upper()} → ${target:.2f}")
            if note is not None:
                p["note"] = note
            save_positions(positions)
            return

    print(f"Posicao aberta em {ticker.upper()} nao encontrada.")


def cmd_clean():
    """Remover posicoes fechadas do ficheiro."""
    positions = load_positions()
    open_positions = [p for p in positions if p["status"] == "open"]
    closed_count = len(positions) - len(open_positions)

    if closed_count == 0:
        print("Nao ha posicoes fechadas para limpar.")
        return

    save_positions(open_positions)
    print(f"{closed_count} posicoes fechadas removidas. {len(open_positions)} abertas mantidas.")


# ============================================================
# Risk Analysis
# ============================================================

def cmd_risk():
    """Analise avancada de risco do portfolio."""
    positions = load_positions()
    open_pos = [p for p in positions if p["status"] == "open"]

    if not open_pos:
        print("Sem posicoes abertas para analisar.")
        return

    tickers = [p["ticker"] for p in open_pos]
    prices = get_current_prices(tickers)

    print(f"\n{'='*60}")
    print(f"  ANALISE DE RISCO DO PORTFOLIO")
    print(f"  {len(open_pos)} posicoes abertas")
    print(f"{'='*60}\n")

    # --- 1. Portfolio Beta ---
    print("1. PORTFOLIO BETA")
    try:
        total_value = 0
        weighted_beta = 0
        for p in open_pos:
            ticker = p["ticker"]
            cp = prices.get(ticker, {}).get("price")
            if not cp:
                continue
            value = p["shares"] * cp
            total_value += value
            try:
                beta = yf.Ticker(ticker).info.get("beta", 1.0)
                if beta is None:
                    beta = 1.0
                weighted_beta += beta * (value / total_value if total_value else 1 / len(open_pos))
            except Exception:
                weighted_beta += 1.0 * (value / total_value if total_value else 1 / len(open_pos))

        if total_value > 0:
            weighted_beta = weighted_beta
            print(f"   Portfolio Beta: {weighted_beta:.2f}")
            if weighted_beta > 1.5:
                print(f"   🔴 Beta elevado — portfolio amplifica movimentos de mercado")
            elif weighted_beta > 1.0:
                print(f"   🟡 Beta > 1 — volatilidade acima do mercado")
            else:
                print(f"   🟢 Beta < 1 — portfolio defensivo")
            print(f"   Valor total estimado: ${total_value:,.2f}")
    except Exception as e:
        print(f"   Erro: {e}")
    print()

    # --- 2. Correlation Matrix ---
    print("2. MATRIZ DE CORRELACAO (3 meses)")
    try:
        # Fetch returns for all positions
        ticker_data = {}
        for ticker in tickers + ["SPY"]:
            try:
                hist = yf.Ticker(ticker).history(period="3mo")
                if not hist.empty and len(hist) > 20:
                    ticker_data[ticker] = hist["Close"].pct_change().dropna()
            except Exception:
                pass

        if len(ticker_data) >= 2:
            # Compute correlation
            tickers_with_data = [t for t in tickers if t in ticker_data]
            if tickers_with_data:
                # Build correlation table
                print("   Ticker  ", end="")
                for t in tickers_with_data:
                    print(f"  {t:6s}", end="")
                print()

                high_corr_pairs = []
                for t1 in tickers_with_data:
                    print(f"   {t1:8s}", end="")
                    for t2 in tickers_with_data:
                        common = ticker_data[t1].index.intersection(ticker_data[t2].index)
                        if len(common) > 10:
                            corr = ticker_data[t1][common].corr(ticker_data[t2][common])
                            print(f"  {corr:5.2f} ", end="")
                            if t1 < t2 and corr > 0.7:
                                high_corr_pairs.append((t1, t2, corr))
                        else:
                            print(f"  {'N/D':5s} ", end="")
                    print()

                if high_corr_pairs:
                    print()
                    print(f"   ⚠️ Alta correlacao (>0.7):")
                    for t1, t2, corr in high_corr_pairs:
                        print(f"      {t1} <-> {t2}: r={corr:.2f}")
    except Exception as e:
        print(f"   Erro: {e}")
    print()

    # --- 3. Profit Factor & Expectancy ---
    print("3. METRICAS DE PERFORMANCE")
    try:
        closed_pos = [p for p in positions if p["status"] == "closed"]
        if closed_pos:
            gross_wins = sum(
                (p.get("exit_price", 0) - p["entry_price"]) * p["shares"]
                for p in closed_pos if p.get("exit_price", 0) > p["entry_price"]
            )
            gross_losses = abs(sum(
                (p.get("exit_price", 0) - p["entry_price"]) * p["shares"]
                for p in closed_pos if p.get("exit_price", 0) <= p["entry_price"]
            ))
            wins = [p for p in closed_pos if p.get("exit_price", 0) > p["entry_price"]]
            losses = [p for p in closed_pos if p.get("exit_price", 0) <= p["entry_price"]]

            win_rate = len(wins) / len(closed_pos) * 100 if closed_pos else 0
            profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

            avg_win = gross_wins / len(wins) if wins else 0
            avg_loss = gross_losses / len(losses) if losses else 0
            expectancy = (win_rate / 100) * avg_win - ((100 - win_rate) / 100) * avg_loss

            print(f"   Trades fechados: {len(closed_pos)} | Win rate: {win_rate:.0f}%")
            print(f"   Profit factor: {profit_factor:.2f}" + (" 🟢" if profit_factor > 1.5 else " 🟡" if profit_factor > 1.0 else " 🔴"))
            print(f"   Avg Win: ${avg_win:.2f} | Avg Loss: ${avg_loss:.2f}")
            print(f"   Expectancy: ${expectancy:.2f} por trade" + (" 🟢" if expectancy > 0 else " 🔴"))
        else:
            print("   Sem trades fechados. Nao ha dados para calcular metricas.")
    except Exception as e:
        print(f"   Erro: {e}")
    print()

    # --- 4. Max Drawdown (simplified) ---
    print("4. DRAWDOWN ESTIMADO (posicoes abertas)")
    try:
        for p in open_pos:
            ticker = p["ticker"]
            if ticker in prices:
                cp = prices[ticker]["price"]
                entry = p["entry_price"]
                pnl_pct = ((cp - entry) / entry) * 100

                # Get historical max adverse excursion
                try:
                    hist = yf.Ticker(ticker).history(period="1mo")
                    if not hist.empty and len(hist) >= 5:
                        hist_low = hist["Low"].min()
                        max_dd = ((entry - hist_low) / entry) * 100
                        print(f"   {ticker}: P&L {pnl_pct:+.1f}% | Max adverse (1m): -{max_dd:.1f}%")
                except Exception:
                    print(f"   {ticker}: P&L {pnl_pct:+.1f}%")
    except Exception as e:
        print(f"   Erro: {e}")
    print()


def cmd_size(ticker, entry, stop, capital=5000, risk_pct=2.0):
    """Calculadora de position sizing."""
    print(f"\n{'='*50}")
    print(f"  POSITION SIZE CALCULATOR: {ticker.upper()}")
    print(f"  Entrada: ${entry:.2f} | Stop: ${stop:.2f}")
    print(f"  Capital: ${capital:,.0f} | Risco max: {risk_pct}%")
    print(f"{'='*50}\n")

    risk_per_share = abs(entry - stop)
    if risk_per_share == 0:
        print("Erro: entry e stop nao podem ser iguais.")
        return

    max_risk_amount = capital * (risk_pct / 100)
    max_shares = int(max_risk_amount / risk_per_share)
    total_cost = max_shares * entry

    # Try to get current price and ATR for context
    try:
        t = yf.Ticker(ticker)
        info = t.info
        current_price = info.get("currentPrice") or info.get("regularMarketPreviousClose", entry)
        hist = t.history(period="1mo")

        if not hist.empty and len(hist) >= 14:
            high = hist["High"]
            low = hist["Low"]
            close = hist["Close"]
            tr1 = high - low
            tr2 = (high - close.shift()).abs()
            tr3 = (low - close.shift()).abs()
            true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]
            atr_pct = (atr / current_price) * 100
            atr_stop_size = int(max_risk_amount / (atr * 2))
            atr_stop_cost = atr_stop_size * entry

            print(f"   Preco atual: ${current_price:.2f}")
            print(f"   ATR (14): ${atr:.2f} ({atr_pct:.1f}%)")
            print()
            print(f"   --- Stop Manual (${stop:.2f}) ---")
            print(f"   Risco/share: ${risk_per_share:.2f}")
            print(f"   Max shares: {max_shares} | Custo: ${total_cost:,.0f}")
            print(f"   R/R com target 2:1: ${entry + 2*risk_per_share:.2f}")
            print()
            print(f"   --- Stop ATR 2x (${entry - atr*2:.2f}) ---")
            print(f"   Risco/share: ${atr*2:.2f}")
            print(f"   Max shares: {atr_stop_size} | Custo: ${atr_stop_cost:,.0f}")
            print()

            if max_shares <= 0:
                print("   ⚠️ Risco por share e maior que o risco maximo — ajusta o stop ou o capital.")
    except Exception:
        print(f"   Risco/share: ${risk_per_share:.2f}")
        print(f"   Max shares: {max_shares} | Custo: ${total_cost:,.0f}")
        print(f"   Target (2:1): ${entry + 2*risk_per_share:.2f}")
        print()


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Portfolio Tracker")
    parser.add_argument("--add", nargs=3, metavar=("TICKER", "SHARES", "ENTRY"),
                       help="Adicionar posicao: TICKER SHARES ENTRY")
    parser.add_argument("--stop", type=float, help="Stop loss (com --add ou --update)")
    parser.add_argument("--target", type=float, help="Take profit (com --add ou --update)")
    parser.add_argument("--note", type=str, help="Nota sobre a posicao")
    parser.add_argument("--close", nargs=2, metavar=("TICKER", "EXIT_PRICE"),
                       help="Fechar posicao: TICKER EXIT_PRICE")
    parser.add_argument("--update", type=str, metavar="TICKER",
                       help="Atualizar stop/target de uma posicao")
    parser.add_argument("--clean", action="store_true", help="Remover posicoes fechadas")
    parser.add_argument("--risk", action="store_true", help="Analise de risco avancada (correlacao, VaR, beta)")
    parser.add_argument("--size", nargs=3, metavar=("TICKER", "ENTRY", "STOP"),
                       help="Calcula position sizing: TICKER ENTRY STOP")
    parser.add_argument("--export", action="store_true", help="Exportar portfolio para CSV")

    args = parser.parse_args()

    if args.add:
        ticker, shares, entry = args.add
        cmd_add(
            ticker,
            int(shares),
            float(entry),
            stop=args.stop,
            target=args.target,
            note=args.note or "",
        )
    elif args.close:
        ticker, exit_price = args.close
        cmd_close(ticker, float(exit_price))
    elif args.update:
        cmd_update(args.update, stop=args.stop, target=args.target, note=args.note)
    elif args.clean:
        cmd_clean()
    elif args.risk:
        cmd_risk()
    elif args.size:
        ticker, entry, stop = args.size
        cmd_size(ticker.upper(), float(entry), float(stop))
    elif args.export:
        positions = load_positions()
        if positions:
            df = pd.DataFrame(positions)
            export_path = REPORTS_DIR / "portfolio_export.csv"
            df.to_csv(export_path, index=False)
            print(f"Exportado para: {export_path}")
        else:
            print("Portfolio vazio.")
    else:
        cmd_show()


if __name__ == "__main__":
    main()
