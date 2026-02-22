# Venus Radar — Changelog

---

## [V3.6] — 2026-02-22

### 🆕 New Features

#### Multi-Timeframe (MTF) Confirmation
The scanner now fetches 1h and 4h candles alongside the core 15m signal. If higher timeframes show a downtrend (price below EMA20 + RSI < 45), the PPAS score is boosted by ×1.15 to confirm the danger. If higher timeframes show strong uptrend, PPAS is moderated by ×0.85 to reduce false positives.  
Config key: `mtf_enabled = true/false`

#### Adaptive Alert Cooldown
During high-volatility market regimes (heat ≥ 30%), alert cooldowns are automatically shortened to 50% or 25% of the configured baseline, ensuring no critical moves are missed.  
Config key: `adaptive_cooldown = true/false`

#### Weighted Ensemble Prediction
Per-coin models now receive **70% weight** and the global model **30%**, replacing the old winner-takes-all logic. This reduces prediction noise for well-trained coins while keeping global model as a safety net.

#### Feature #12: Volume Climax Score
A new `volume_climax_score` feature detects abnormal volume spikes at the end of sustained directional moves — a classic blow-off top or capitulation signal. Added to both `train_ppas.py` and `pdrs_calculator.py`.

#### Walk-Forward Validation
`train_ppas.py` now runs 3-fold time-series cross-validation before saving the global model. Reports OOS AUC per fold to help detect overfitting across time.

#### Probability Calibration
Global model probabilities are now calibrated using `CalibratedClassifierCV` (isotonic regression), resulting in more reliable PPAS score distributions.

#### Dynamic ATR Zone Table
Alert zones now scale with PPAS tier:
- PPAS ≥ 92: ATR × 3.5–6.0
- PPAS 80–92: ATR × 2.7–4.5  
- PPAS 60–80: ATR × 2.0–3.5
- PPAS < 60: ATR × 1.5–2.5

#### Telegram Improvements
- Rate-limit guard: minimum 1.2s between sends with auto-retry on 429
- Long messages auto-split into chunks to avoid 4096-char limit
- MTF filter tag shown in alerts (▲ Confirmed / ▼ Dampened)
- Adaptive cooldown duration shown in alert header

#### Console UI
- Color-coded PPAS column (🔴 high / 🟡 medium / 🟢 low)
- Added RSI and Sigma columns to Top 10 table
- MTF multiplier column added
- Progress bar now shows fetch mode (FULL / INCREMENTAL)

#### Daily Recap Upgraded
- Now includes AI Win-Rate for the day (from `prediction_outcomes` table)
- MTF multiplier shown per coin in recap list

---

### 🔧 Improvements

#### `data_fetcher.py`
- Retry with exponential backoff (up to 3 attempts per symbol)
- Per-candle validation rejects malformed OHLCV rows before DB insert
- Auto-prune: candles older than 90 days removed to keep DB lean
- DB index added on `(symbol, timeframe, timestamp_ms)` for faster incremental queries
- Daily rotating log file in `logs/`

#### `pdrs_calculator.py`
- Added **Trend Context Modifier (TCM)**: uptrend → ×0.90 danger, downtrend → ×1.15
- Added **Volume Climax Detection** as a 5% weighted KPI
- Parabolic Extension weight reduced from 30% → 25% (distributed to climax)
- Detail string now includes Climax score and TCM multiplier
- Extended coin mapping (AVAX, ATOM, NEAR, APT, ARB, OP, SUI, SEI, TIA added)

#### `train_ppas.py`
- Feature list expanded from 11 → 12 (volume_climax_score)
- Feature importance logged after global model training
- Better progress reporting during feature engineering loop
- English logging throughout (no more mixed Vietnamese/English)
- `sys` import moved to top level

#### `ml_retrain.py`
- Full English logging
- Uses `sys.executable` for subprocess calls (respects virtual environments)
- Log output to both file and console simultaneously

---

### 🗄️ Database Schema Changes

**`live_predictions` table** — new columns (auto-migrated on first run):
- `mtf_mult REAL DEFAULT 1.0` — MTF bias multiplier applied to this prediction
- `ppas_adj INTEGER DEFAULT 0` — delta between raw and MTF-adjusted PPAS

**New table: `prediction_outcomes`**
```sql
CREATE TABLE prediction_outcomes (
    ts              INTEGER,
    symbol          TEXT,
    ppas_at_alert   INTEGER,
    price_at_alert  REAL,
    price_4h_later  REAL,
    outcome         TEXT,
    PRIMARY KEY(ts, symbol)
)
```

---

### ⚙️ Config Changes (`config.ini`)

New keys in `[RADAR]`:
```ini
top_scan_coins = 100     ; how many coins to scan per cycle
mtf_enabled = true       ; enable multi-timeframe filter
adaptive_cooldown = true ; shorten cooldown during high-volatility regimes
```

---

### 📦 File Renamed
`Venus_Radar_V3.py` → `Venus_Radar_V3.6.py`  
`Venus_Radar_V3.bat` → `Venus_Radar_V3.6.bat`

---

## [V3.0] — Initial Release
- 11-feature Random Forest PPAS scoring
- Per-coin + Global model ensemble
- Bybit L/S Ratio integration
- MLOps: Hard Example Mining
- Telegram alerts with Smart Mute
- Daily Risk Recap
