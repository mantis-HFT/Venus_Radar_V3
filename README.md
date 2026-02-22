# 📡 Venus Radar V3.6 — AI Crypto Risk Scanner

An AI-powered real-time crypto risk detection system built on Bybit, using a Random Forest ML model with 12 engineered KPIs to predict dangerous price moves before they happen.

---

## 🆕 What's New in V3.6

| Feature | Description |
|---|---|
| **Multi-Timeframe (MTF) Confirmation** | 1h + 4h bias filter adjusts PPAS ×0.85–×1.15 to reduce false signals |
| **Adaptive Cooldown** | Alert cooldowns shorten automatically in high-volatility regimes |
| **Weighted Ensemble** | Per-coin model 70% + Global model 30% for better predictions |
| **Feature #12: Volume Climax** | Detects blow-off tops / capitulation via volume spike × trend strength |
| **Walk-Forward Validation** | 3-fold time-series OOS AUC reported during training |
| **Probability Calibration** | Isotonic regression calibration on global model probabilities |
| **Dynamic ATR Zones** | Alert zones scale with PPAS tier (4 tiers) |
| **Telegram Rate Guard** | Auto-retry on 429, message chunking for long alerts |
| **Color Console UI** | PPAS color-coded, RSI + Sigma columns added to Top 10 |

See [CHANGELOG.md](CHANGELOG.md) for full details.

---

## 🏗️ Project Structure

```
Venus_Radar_V3.6/
├── Venus_Radar_V3.6.py        # Main scanner (run this)
├── Venus_Radar_V3.6.bat       # Windows auto-loop launcher
├── auto_retrain_loop.bat      # 7-day ML retrain loop
├── ml_retrain.py              # Python retrain pipeline launcher
├── pdrs_calculator.py         # PDRS risk score engine
├── config.ini                 # All configuration
├── CHANGELOG.md
├── README.md
└── ml_enhancements/
    ├── data_fetcher.py        # Async OHLCV fetcher (Bybit)
    ├── train_ppas.py          # ML training pipeline
    ├── ppas_global_model.pkl  # (generated after training)
    └── models/                # (per-coin models, generated after training)
```

---

## ⚙️ Setup

### 1. Install Dependencies
```bash
pip install ccxt pandas numpy scikit-learn joblib requests pycoingecko colorama
```

### 2. Configure
Edit `config.ini`:
```ini
[TELEGRAM]
bot_token = YOUR_BOT_TOKEN
chat_id   = YOUR_CHAT_ID
```

### 3. Fetch Data & Train Model (first time)
```bash
python ml_enhancements/data_fetcher.py
python ml_enhancements/train_ppas.py
```
This will create `Venus_Market_Data.db` and train both the global model and per-coin models.

### 4. Run the Scanner
**Option A — Single scan:**
```bash
python Venus_Radar_V3.6.py --oneshot
```

**Option B — Continuous loop (Python):**
```bash
python Venus_Radar_V3.6.py
```

**Option C — Windows auto-loop (recommended):**
Double-click `Venus_Radar_V3.6.bat`

### 5. Set Up Auto-Retraining (Optional)
Double-click `auto_retrain_loop.bat` — retrains the model every 7 days automatically.

---

## 📊 How PPAS Works

**PPAS** (Parabolic Price Action Score) is a 0–100 risk score produced by the AI model. It is derived from 12 engineered features:

| # | Feature | Description |
|---|---|---|
| 1 | dev_pct | % deviation from 200-period SMA |
| 2 | streak_penalty | Penalty for sustained one-directional streaks |
| 3 | sigma_distance | Z-score of current candle vs 1-week volatility |
| 4 | rsi | RSI (56-period) |
| 5 | volatility | Rolling 20-candle log return std |
| 6 | atr_pct | ATR (56) as % of price |
| 7 | volume_surge | Current volume / 20-period avg volume |
| 8 | onchain_proxy | Current volume / 100-period avg volume |
| 9 | liq_attention | (High - Low) / Volume |
| 10 | ls_ratio | Live Long/Short ratio from Bybit API |
| 11 | rp | Rebound Probability heuristic |
| 12 | volume_climax_score | Volume spike × trend consistency (v3.6) |

**MTF Multiplier** (v3.6): After prediction, the raw PPAS is multiplied by 0.85–1.15 based on 1h + 4h trend confirmation.

---

## 🔧 Key Config Options

```ini
[RADAR]
risk_threshold_high = 92    ; PPAS above this → alert sent
risk_threshold_safe = 82    ; PPAS below this → recovery alert
alert_cooldown = 14400      ; seconds between repeat alerts (4h default)
top_scan_coins = 100        ; how many coins to scan per cycle
mtf_enabled = true          ; enable Multi-Timeframe filter
adaptive_cooldown = true    ; shorten cooldown in volatile markets

[MACHINE_LEARNING]
n_estimators = 150
max_depth = 12
min_samples_per_coin = 2000 ; minimum rows to train a per-coin model
future_window = 12          ; candles ahead for label generation
risk_sigma_threshold = 3.0  ; sigma multiplier for adaptive labeling
```

---

## 📬 Telegram Alert Format

```
📡 Venus Radar V3.6 — Feb-22 14:30 | ⚡ Adaptive Cooldown: 60m

⛔ BTCUSDT 🧠 [PerCoin]
PPAS: 95 | Dev: +18.2% | RSI: 78.4
L/S Ratio: 1.82x | Vol Surge: 3.4x
Sigma: 4.21σ | VR: 2.8%
Price: $98,500
MTF Filter: ▲ Confirmed (×1.15)
🎯 Up Zone:   $101,200 → $105,800
🕳️ Down Zone: $95,100 → $90,500
```

---

## 📈 Daily Recap

Sent automatically at the configured `recap_hour_gmt7`. Includes:
- All coins flagged during the day with peak PPAS
- AI win-rate for the session (correct high-risk predictions vs outcomes)

---

## ⚠️ Disclaimer

This tool is for **informational and educational purposes only**. It does not constitute financial advice. Crypto markets are extremely volatile. Always do your own research before making any trading decisions.
