"""
Portfolio tracker — tracking de posicoes abertas, P&L, metricas de risco.
Uso:
  python portfolio_tracker.py                     (ver portfolio atual)
  python portfolio_tracker.py --add AAPL 10 150.00 140.00    (adicionar posicao)
  python portfolio_tracker.py --close AAPL 165.00            (fechar posicao)
  python portfolio_tracker.py --update AAPL stop=148.00      (atualizar stop)
  python portfolio_tracker.py --clean                        (remover posicoes fechadas)
Ficheiro de posicoes: ../positions.json
"""
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import POSITIONS_FILE, REPORTS_DIR, ensure_dirs

try:
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
