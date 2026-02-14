# Venus Radar V2 - Quick Start Guide

## Installation (3 steps)

### Step 1: Install Python
Make sure you have Python 3.8 or higher installed.

Check with:
```bash
python --version
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Choose Your Version

You have **two options**:

#### Option A: Simple Version (Recommended for Beginners)
Use `venus_radar_v2.py` - all settings are in the code

```bash
python venus_radar_v2.py
```

To customize, edit the `main()` function in the file.

#### Option B: Config File Version (Recommended)
Use `venus_radar_v2_config.py` + `config.py`

1. Edit settings in `config.py`
2. Run the scanner:
```bash
python venus_radar_v2_config.py
```

## Quick Configuration

### Change Exchange
Edit `config.py`:
```python
EXCHANGE = 'binance'  # or 'bybit'
```

### Change Scan Interval
Edit `config.py`:
```python
SCAN_INTERVAL_MINUTES = 5  # Scan every 5 minutes
```

### Enable Telegram Alerts

1. **Create a Telegram bot:**
   - Open Telegram
   - Search for @BotFather
   - Send `/newbot`
   - Follow instructions
   - Copy your bot token

2. **Get your chat ID:**
   - Search for @userinfobot
   - Send `/start`
   - Copy your ID

3. **Update config.py:**
```python
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = "123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
TELEGRAM_CHAT_ID = "123456789"
```

## First Run

When you first run the scanner:

1. **It will create a database** (`pdrs_venus_radar_v2.db`)
2. **Scan immediately** (takes 30-90 seconds)
3. **Display top 10 coins** by PPAS score
4. **Show any alerts** if found
5. **Wait 10 minutes** and repeat

## Understanding the Output

### Example Console Output:
```
================================================================================
Venus Radar scan - 2024-02-08 14:30:00
================================================================================
Fetching top futures by volume...
Found 100 coins
Applying smart filter...
Filtered to 42 coins for analysis
Analyzing 42 coins...

================================================================================
TOP 10 COINS BY PPAS
================================================================================

1. BTC/USDT
   PPAS: 78.45          ← Risk score (0-100, higher = more risk)
   Deviation: 12.34%    ← How far from average price
   RP: 45.67            ← Reversal potential (lower = higher risk)
   24h Volume: $12,345,678,901
   Window: 4h           ← Time window analyzed

2. ETH/USDT
   PPAS: 72.31
   ...

================================================================================
⚠️  2 ALERTS
================================================================================

POTENTIAL RISK: BTC/USDT
   PPAS: 78.45
   Deviation: 12.34%
   RP: 45.67

HIGH RISK: SHIB/USDT [REPEAT]  ← Already alerted in last 2 hours
   PPAS: 88.12
   Deviation: 18.90%
   RP: 28.45
```

## What Do the Scores Mean?

### PPAS (Potential Pump Alert Score)
- **0-50:** Low risk
- **50-75:** Moderate risk
- **75-85:** Potential risk ⚠️
- **85-100:** High risk 🚨

### Deviation
- How far the current price is from its recent average
- **>10%:** Significant move
- **>15%:** Extreme move

### RP (Reversal Potential)
- **100:** Very stable, no reversal signs
- **50-100:** Normal range
- **<50:** Warning - possible reversal coming
- **<30:** High reversal risk

## Common Issues

### "No coins fetched"
**Solution:** Check your internet connection or try the other exchange

### "Not enough data for symbol"
**Solution:** This is normal for new coins - they'll be skipped automatically

### All PPAS scores are very low
**Solution:** This is currently expected. The scoring needs calibration. The system still works - it will alert when scores are relatively high.

### Rate limit errors
**Solution:** Increase `SCAN_INTERVAL_MINUTES` in config.py

## File Structure

```
your-folder/
├── venus_radar_v2.py              # Simple version (standalone)
├── venus_radar_v2_config.py       # Config version (recommended)
├── config.py                      # Settings file
├── requirements.txt               # Dependencies
├── README.md                      # Full documentation
├── QUICKSTART.md                  # This file
└── pdrs_venus_radar_v2.db        # Database (auto-created)
```

## Running 24/7

### On Linux/Mac:
Use `screen` or `tmux`:
```bash
screen -S venus
python venus_radar_v2_config.py

# Press Ctrl+A then D to detach
# To reattach: screen -r venus
```

### On Windows:
Use a service or just keep the terminal open.

### On a VPS:
Same as Linux, or use systemd service.

## Testing Before Running

Run a single scan without the loop:

```python
# In venus_radar_v2_config.py, change the last line:
if __name__ == "__main__":
    radar = VenusRadar()
    radar.run_scan()  # Just run once instead of loop
```

## Getting Help

1. Check the logs in the console
2. Look in the database: `sqlite3 pdrs_venus_radar_v2.db`
3. Read the full README.md for details
4. Check the code comments

## Safety Reminder

⚠️ This is a **detection tool**, not trading advice.
- Always do your own research
- Use proper risk management
- Never invest more than you can lose

## Next Steps

After running for a while:
1. Review the database for patterns
2. Adjust thresholds in config.py
3. Monitor which coins actually reverse
4. Fine-tune settings based on results

---

**Need more details?** See README.md for complete documentation.

**Ready to start?**
```bash
python venus_radar_v2_config.py
```
