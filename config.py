"""
Configuration file for Venus Radar V2
Edit these values to customize your scanner
"""

# === EXCHANGE SETTINGS ===
EXCHANGE = 'bybit'  # Options: 'bybit' or 'binance'

# === SCANNING SETTINGS ===
SCAN_INTERVAL_MINUTES = 10  # How often to run scans (5, 10, 15, 30, etc.)
MAX_WORKERS = 10  # Parallel processing threads (higher = faster but more CPU)

# === ALERT THRESHOLDS ===
# High Risk Alert
HIGH_RISK_PPAS = 85  # PPAS score threshold
HIGH_DEVIATION_THRESHOLD = 15.0  # Price deviation % from average
VERY_LOW_RP_THRESHOLD = 30  # Reversal Potential threshold

# Potential Risk Alert  
POTENTIAL_RISK_PPAS = 75  # PPAS score threshold
MEDIUM_DEVIATION_THRESHOLD = 10.0  # Price deviation %
LOW_RP_THRESHOLD = 50  # Reversal Potential threshold

# === FILTERING SETTINGS ===
TOP_VOLUME_COUNT = 100  # How many coins to fetch initially
TOP_GAINERS_COUNT = 30  # How many top gainers to analyze
TOP_LOSERS_COUNT = 10  # How many top losers to analyze

# === TELEGRAM NOTIFICATIONS ===
TELEGRAM_ENABLED = False  # Set to True to enable Telegram alerts

# Get these from @BotFather and @userinfobot on Telegram
TELEGRAM_BOT_TOKEN = ""  # Your bot token (e.g., "123456789:ABCdefGHI...")
TELEGRAM_CHAT_ID = ""  # Your chat ID (e.g., "123456789")

# === DATABASE ===
DATABASE_PATH = "pdrs_venus_radar_v2.db"

# === LOGGING ===
LOG_LEVEL = "INFO"  # Options: DEBUG, INFO, WARNING, ERROR
LOG_TO_FILE = False  # Set to True to also log to file
LOG_FILE_PATH = "venus_radar.log"

# === PPAS CALCULATION TWEAKS ===
# Adjust these if you want to fine-tune the scoring algorithm
PPAS_MULTIPLIER = 1.8  # Temporary boost to scores (1.0 = no boost)

# Component weights (must sum to ~1.0)
PPAS_WEIGHTS = {
    'n_vr': 0.15,   # Volatility
    'n_laf': 0.15,  # Liquidity Attention Factor
    'n_sci': 0.15,  # Social/Community Interest  
    'n_hms': 0.10,  # High Momentum Spike
    'n_lvr': 0.10,  # Largest Volume Ratio
    'n_sbr': 0.15,  # Short-term Burst Ratio
    'n_vpr': 0.10,  # Volume Pattern Ratio
    'n_tams': 0.10, # Technical Analysis Momentum
    'n_ocai': 0.10, # On-Chain Activity Indicator
    'rp': 0.15      # Reversal Potential
}

# === ADVANCED SETTINGS ===
# Time windows to analyze (in hours)
ANALYSIS_WINDOWS = [4, 2, 1]

# Minimum candles required
MIN_CANDLES = 4

# Data fetch limits
CANDLES_LIMIT = 200  # Max historical candles to fetch

# Alert cooldown (hours) - prevents spam for same coin
ALERT_COOLDOWN_HOURS = 2
