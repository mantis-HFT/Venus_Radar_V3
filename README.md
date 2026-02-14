# Venus Radar V2 - Crypto Futures Risk Scanner

A real-time risk detection system for cryptocurrency perpetual futures that identifies potential reversals and overextension risks.

## Overview

Venus Radar monitors crypto futures markets (Bybit/Binance) every 10 minutes to detect coins showing signs of:
- Potential price reversals
- Overextension risk
- Unusual volume spikes
- Momentum exhaustion

It calculates a **PPAS (Potential Pump Alert Score)** from 0-100 that indicates risk level.

## Features

- ✅ Multi-exchange support (Bybit, Binance)
- ✅ Parallel processing of multiple coins
- ✅ Smart filtering (top gainers + losers)
- ✅ SQLite database for tracking alerts
- ✅ Telegram notifications (optional)
- ✅ Customizable alert thresholds
- ✅ 10-minute automated scanning

## Installation

### 1. Install Python 3.8+

Make sure you have Python 3.8 or higher installed.

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install ccxt pandas numpy requests
```

### 3. Configure Settings

Open `venus_radar_v2.py` and modify the configuration in the `main()` function:

```python
config = AlertConfig(
    HIGH_RISK_PPAS=85,              # PPAS threshold for high risk alerts
    POTENTIAL_RISK_PPAS=75,         # PPAS threshold for potential risk
    HIGH_DEVIATION_THRESHOLD=15.0,  # High price deviation %
    MEDIUM_DEVIATION_THRESHOLD=10.0, # Medium price deviation %
    VERY_LOW_RP_THRESHOLD=30,       # Very low reversal potential
    LOW_RP_THRESHOLD=50,            # Low reversal potential
    
    # Telegram settings (optional)
    TELEGRAM_ENABLED=False,         # Set to True to enable
    TELEGRAM_BOT_TOKEN="",          # Your Telegram bot token
    TELEGRAM_CHAT_ID=""             # Your Telegram chat ID
)
```

### 4. Choose Exchange

In the `main()` function, set your preferred exchange:

```python
exchange = 'bybit'  # or 'binance'
```

## Usage

### Run the Scanner

```bash
python venus_radar_v2.py
```

The scanner will:
1. Run immediately on start
2. Repeat every 10 minutes automatically
3. Display top 10 coins by PPAS score
4. Generate alerts for high-risk situations
5. Log all data to SQLite database

### Output Example

```
================================================================================
Starting Venus Radar scan - 2024-02-08 14:30:00
================================================================================
Fetching top 100 futures by volume...
Found 100 coins
Applying smart filter (top gainers + losers)...
Filtered to 42 coins for analysis
Analyzing 42 filtered coins...

================================================================================
TOP 10 COINS BY PPAS SCORE
================================================================================

1. BTC/USDT
   PPAS: 78.45
   Deviation: 12.34%
   RP Score: 45.67
   24h Volume: $12,345,678,901
   Window: 4h

2. ETH/USDT
   PPAS: 72.31
   ...

================================================================================
⚠️  2 ALERTS GENERATED
================================================================================

POTENTIAL RISK: BTC/USDT
   PPAS: 78.45
   Deviation: 12.34%
   RP: 45.67

HIGH RISK: SHIB/USDT [REPEAT]
   PPAS: 88.12
   Deviation: 18.90%
   RP: 28.45
```

## Alert Levels

### HIGH RISK 🚨
Triggered when:
- PPAS ≥ 85, OR
- Deviation ≥ 15% AND RP < 30

**Action:** Consider pausing grid bots, reducing position size, or exiting

### POTENTIAL RISK ⚠️
Triggered when:
- PPAS ≥ 75, OR  
- Deviation ≥ 10% AND RP < 50

**Action:** Monitor closely, prepare to reduce exposure

## PPAS Score Components

The PPAS score (0-100) is calculated from 10 weighted metrics:

| Component | Description | Weight |
|-----------|-------------|--------|
| **n_vr** | Volatility (annualized) | 15% |
| **n_laf** | Liquidity Attention Factor | 15% |
| **n_sci** | Social/Community Interest | 15% |
| **n_hms** | High Momentum Spike (recent vs avg volume) | 10% |
| **n_lvr** | Largest Volume Ratio (max spike) | 10% |
| **n_sbr** | Short-term Burst Ratio (1h vs overall) | 15% |
| **n_vpr** | Volume Pattern Ratio (short vs long term) | 10% |
| **n_tams** | Technical Analysis Momentum (RSI + SMA) | 10% |
| **n_ocai** | On-Chain Activity Indicator (volume proxy) | 10% |
| **rp** | Reversal Potential (inverted: low RP = high risk) | 15% |

**Reversal Potential (RP)** is calculated as:
```
RP = 100 - (streak_penalty) - (deviation_penalty)
```

Where:
- **Streak penalty:** Consecutive up/down candles (×5 per candle, max 30)
- **Deviation penalty:** Distance from moving average (×2 per %, max 40)

Lower RP = Higher risk of reversal

## Database

The scanner creates `pdrs_venus_radar_v2.db` with three tables:

- **alerts_history:** All generated alerts with timestamps
- **price_cache:** Cached OHLCV data (for future optimization)
- **coin_rankings:** Complete PPAS rankings for each scan

You can query this database for historical analysis.

## Telegram Setup (Optional)

### 1. Create a Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow instructions
3. Copy your bot token (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Get Your Chat ID

1. Search for [@userinfobot](https://t.me/userinfobot) on Telegram
2. Send `/start`
3. Copy your chat ID (a number)

### 3. Enable in Config

```python
TELEGRAM_ENABLED=True,
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
TELEGRAM_CHAT_ID="123456789"
```

## Customization

### Change Scan Interval

Modify in `main()`:
```python
radar.run_loop(interval_minutes=10)  # Change to 5, 15, 30, etc.
```

### Adjust Filter Count

In `get_smart_filtered_coins()`:
```python
top_gainers = [c['symbol'] for c in changes[:30]]  # Change 30
top_losers = [c['symbol'] for c in changes[-10:]]  # Change 10
```

### Modify PPAS Calculation

The core logic is in the `calculate_ppas()` method. You can:
- Adjust weights for each component
- Change normalization factors
- Add new indicators
- Modify the temporary 1.8x boost

## Troubleshooting

### "No coins fetched"
- Check internet connection
- Verify exchange API is accessible
- Try switching exchange (bybit ↔ binance)

### "Not enough data for symbol"
- Normal for newly listed coins
- Scanner will skip and continue

### Rate limits
- CCXT has built-in rate limiting
- If issues persist, increase scan interval

### Low PPAS scores
- This is currently expected (see document)
- The scoring formula may need tuning
- Monitor the raw component values in logs

## Performance Notes

- **Scan time:** ~30-90 seconds for 40 coins (parallel processing)
- **Memory:** ~100-200 MB
- **Database:** Grows ~1 MB per day (approximate)
- **CPU:** Low (mostly I/O bound)

## Known Issues

1. **PPAS scores tend to be low** - Volume-based metrics need tuning
2. **Fixed components** (LAF, SCI) don't add value yet
3. **Needs more live testing** to calibrate thresholds

## Roadmap

- [ ] Add CoinGecko/CoinMarketCap integration for LAF/SCI
- [ ] Implement adaptive thresholds based on market conditions
- [ ] Add backtesting module
- [ ] Web dashboard for monitoring
- [ ] Multi-timeframe correlation analysis
- [ ] Machine learning score optimization

## Safety Disclaimer

⚠️ **This is a risk detection tool, NOT financial advice.**

- Always do your own research
- Use proper risk management
- Never invest more than you can afford to lose
- Past performance doesn't guarantee future results
- Crypto trading is highly risky

## License

This is free software. Use at your own risk.

## Support

For issues or questions:
1. Check the logs in the console output
2. Examine the SQLite database for historical data
3. Review the code comments for implementation details

---

**Version:** 2.0  
**Last Updated:** February 2024
