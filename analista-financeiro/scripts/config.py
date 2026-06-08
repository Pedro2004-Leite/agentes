"""
Configuracao central para os scripts financeiros.
Editado manualmente ou pelo agente.
"""
import os
from pathlib import Path

# ---- Paths ----
SCRIPT_DIR = Path(__file__).parent.absolute()
AGENT_DIR = SCRIPT_DIR.parent
REPORTS_DIR = AGENT_DIR / "reports"

# ---- API Keys (opcional — yfinance nao precisa) ----
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")

# ---- Watchlist (tickers a monitorizar diariamente) ----
WATCHLIST = [
    # Adiciona tickers aqui, ex: "AAPL", "MSFT", "NVDA"
]

# ---- Indices de referencia ----
BENCHMARKS = ["^GSPC", "^IXIC", "^VIX"]  # S&P 500, NASDAQ, VIX

# ---- Screening defaults ----
DEFAULT_SCREENER_UNIVERSE = "sp500"  # "sp500", "nasdaq100", ou lista de tickers

# ---- Relatorio ----
# Numero de anos de dados historicos para analise
ANOS_HISTORICOS = 5


def ensure_dirs():
    """Criar directorias necessarias."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_report_path(ticker: str, date_str: str) -> Path:
    """Caminho para guardar um relatorio."""
    ticker_clean = ticker.replace("^", "").upper()
    dir_path = REPORTS_DIR / date_str
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / f"{ticker_clean}.md"


def get_briefing_path(date_str: str) -> Path:
    """Caminho para o briefing do dia."""
    dir_path = REPORTS_DIR / date_str
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / "briefing.md"
