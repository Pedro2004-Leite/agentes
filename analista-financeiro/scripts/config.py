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
POSITIONS_FILE = AGENT_DIR / "positions.json"

# ---- API Keys (opcional — yfinance nao precisa) ----
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")

# ---- Watchlist (tickers a monitorizar diariamente) ----
WATCHLIST = [
    # Tecnologia
    "AAPL", "MSFT", "NVDA", "AMD", "AVGO",
    # Financeiras / Fintech
    "JPM", "V", "MA", "PYPL",
    # Consumo / Industriais
    "AMZN", "TSLA", "RACE", "LVMUY",
    # Energia / Commodities
    "XOM", "GLEN.L",
    # Defesa / Aeroespacial
    "RTX", "LMT",
    # Biotech / Saude
    "ABBV", "JNJ",
]

# ---- Indices de referencia ----
BENCHMARKS = [
    # EUA
    "^GSPC",   # S&P 500
    "^IXIC",   # NASDAQ Composite
    "^DJI",    # Dow Jones
    "^RUT",    # Russell 2000
    "^VIX",    # Volatility Index
    # Europa
    "^STOXX50E",  # Euro Stoxx 50
    "^GDAXI",     # DAX (Alemanha)
    "^FTSE",      # FTSE 100 (Reino Unido)
    "^FCHI",      # CAC 40 (Franca)
    "PSI20.LS",   # PSI-20 (Portugal)  # Pode falhar no yfinance, fallback abaixo
    "^V2TX",      # VSTOXX (volatilidade europeia)
]

# ---- FX e Commodities ----
MACRO_MONITORS = [
    "EURUSD=X",  # Euro/Dolar
    "GC=F",      # Ouro
    "CL=F",      # Petroleo WTI
    "TNX",       # Yield 10Y EUA
]

# ---- Screening defaults ----
DEFAULT_SCREENER_UNIVERSE = "sp500"  # "sp500", "nasdaq100", "eurostoxx50", ou lista de tickers

# ---- Relatorio ----
ANOS_HISTORICOS = 5  # Numero de anos de dados historicos para analise

# ---- Risk Management ----
MAX_RISK_PER_TRADE_PCT = 2.0  # Risco maximo por trade em % do capital
MIN_RISK_REWARD_RATIO = 2.0   # Risk/reward minimo recomendado


def ensure_dirs():
    """Criar directorias necessarias."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_report_path(ticker: str, date_str: str) -> Path:
    """Caminho para guardar um relatorio."""
    ticker_clean = ticker.replace("^", "").replace("=", "").replace(".", "-").upper()
    dir_path = REPORTS_DIR / date_str
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / f"{ticker_clean}.md"


def get_briefing_path(date_str: str) -> Path:
    """Caminho para o briefing do dia."""
    dir_path = REPORTS_DIR / date_str
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / "briefing.md"


def get_screener_path(date_str: str) -> Path:
    """Caminho para resultados do screener."""
    dir_path = REPORTS_DIR / date_str
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / "screener.md"
