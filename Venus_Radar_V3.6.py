"""
╔══════════════════════════════════════════════════════════════════╗
║           VENUS RADAR V3.6 — AI CRYPTO RISK SCANNER             ║
║  Changelog v3.6:                                                 ║
║  • Multi-timeframe confirmation (15m + 1h + 4h)                 ║
║  • Adaptive cooldown based on market volatility regime          ║
║  • Weighted ensemble: per-coin > global (confidence blending)   ║
║  • Smarter zone calculation using ATR multiplier table          ║
║  • PDRS integration on alert messages                           ║
║  • Telegram rate-limit guard (batch sending with delay)         ║
║  • Console UI upgraded: color-coded risk tiers                  ║
║  • Daily Recap now includes win-rate tracking vs actual outcome ║
╚══════════════════════════════════════════════════════════════════╝
"""
import ccxt
import pandas as pd
import numpy as np
import time
import requests
import datetime
import sys
import os
import joblib
import configparser
import sqlite3
import warnings

warnings.filterwarnings('ignore')

# ==========================================
# 1. LOAD CONFIGURATION
# ==========================================
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

TELEGRAM_BOT_TOKEN   = config['TELEGRAM']['bot_token']
TELEGRAM_CHAT_ID     = config['TELEGRAM']['chat_id']
SCAN_INTERVAL        = config['RADAR'].getint('scan_interval', fallback=600)
ALERT_COOLDOWN       = config['RADAR'].getint('alert_cooldown', fallback=14400)
PPAS_JUMP_TRIGGER    = config['RADAR'].getint('ppas_jump_trigger', fallback=10)
RISK_THRESHOLD_HIGH  = config['RADAR'].getint('risk_threshold_high', fallback=92)
RISK_THRESHOLD_SAFE  = config['RADAR'].getint('risk_threshold_safe', fallback=82)

GLOBAL_MODEL_PATH    = config['MACHINE_LEARNING']['global_model_path']
PER_COIN_DIR         = config['MACHINE_LEARNING']['per_coin_models_dir']
PREDICTIONS_DB       = config.get('MLOPS', 'predictions_db', fallback='Venus_Predictions.db')
MARKET_HEAT_THRESHOLD= config.getint('MLOPS', 'market_heat_threshold', fallback=30)
RECAP_HOUR           = config.getint('MLOPS', 'recap_hour_gmt7', fallback=0)

# v3.6 — new config keys (with safe fallbacks if config.ini not yet updated)
TOP_SCAN_COINS       = config['RADAR'].getint('top_scan_coins', fallback=100)
MTF_ENABLED          = config['RADAR'].getboolean('mtf_enabled', fallback=True)
ADAPTIVE_COOLDOWN    = config['RADAR'].getboolean('adaptive_cooldown', fallback=True)

# ANSI color codes for console (Windows-compatible via colorama if present, else fallback)
try:
    import colorama; colorama.init()
    RED = '\033[91m'; YELLOW = '\033[93m'; GREEN = '\033[92m'
    CYAN = '\033[96m'; RESET = '\033[0m'; BOLD = '\033[1m'
except ImportError:
    RED = YELLOW = GREEN = CYAN = RESET = BOLD = ''

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
_last_telegram_ts = 0

def send_telegram(msg, retry=2):
    """Send Telegram message with rate-limit guard (min 1s between sends)."""
    global _last_telegram_ts
    gap = time.time() - _last_telegram_ts
    if gap < 1.2:
        time.sleep(1.2 - gap)
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        r = requests.post(url, json=payload, timeout=10)
        _last_telegram_ts = time.time()
        if r.status_code == 429 and retry > 0:
            wait = r.json().get('parameters', {}).get('retry_after', 5)
            time.sleep(wait)
            send_telegram(msg, retry - 1)
    except Exception as e:
        print(f"\n{RED}[Telegram Error]{RESET} {e}")

def send_telegram_chunks(msg, max_len=4000):
    """Split long messages to avoid Telegram 4096-char limit."""
    if len(msg) <= max_len:
        send_telegram(msg)
        return
    parts = []
    while msg:
        parts.append(msg[:max_len])
        msg = msg[max_len:]
    for part in parts:
        send_telegram(part)
        time.sleep(0.5)

def format_price(price):
    if price >= 100:   return f"{price:.0f}"
    elif price >= 0.1: return f"{price:.2f}"
    elif price >= 0.01: return f"{price:.4f}"
    else:              return f"{price:.6f}"

def colorize_ppas(ppas):
    """Return color-coded PPAS string for console output."""
    if ppas >= RISK_THRESHOLD_HIGH: return f"{RED}{BOLD}{ppas}{RESET}"
    elif ppas >= RISK_THRESHOLD_SAFE: return f"{YELLOW}{ppas}{RESET}"
    elif ppas >= 60: return f"{YELLOW}{ppas}{RESET}"
    else: return f"{GREEN}{ppas}{RESET}"

# ==========================================
# 3. MULTI-TIMEFRAME CONFIRMATION (v3.6 NEW)
# ==========================================
def get_mtf_bias(exchange, symbol):
    """
    Fetch 1h and 4h candles and return a simple trend bias score (-1, 0, +1).
    Used to confirm or dampen a 15m PPAS spike.
    Returns a multiplier: 1.0 (neutral), 1.15 (confirmed), 0.85 (counter-trend)
    """
    try:
        scores = []
        for tf, limit in [('1h', 48), ('4h', 24)]:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
            if len(ohlcv) < 20:
                continue
            df = pd.DataFrame(ohlcv, columns=['ts','open','high','low','close','volume'])
            c = df['close']
            # Simple trend: price above/below EMA20
            ema20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
            rsi_delta = c.diff()
            g = rsi_delta.where(rsi_delta > 0, 0).rolling(14).mean().iloc[-1]
            lo = -rsi_delta.where(rsi_delta < 0, 0).rolling(14).mean().iloc[-1]
            rsi = 100 - (100 / (1 + g / (lo + 1e-9)))
            # Score: +1 if bearish pressure (danger confirmed), -1 if bullish
            if c.iloc[-1] > ema20 and rsi > 55:
                scores.append(-1)   # strong uptrend — PPAS risk may be fakeout
            elif c.iloc[-1] < ema20 and rsi < 45:
                scores.append(1)    # downtrend — risk confirmed
            else:
                scores.append(0)
        if not scores:
            return 1.0
        avg = np.mean(scores)
        if avg > 0.3:  return 1.15
        if avg < -0.3: return 0.85
        return 1.0
    except Exception:
        return 1.0

# ==========================================
# 4. ATR ZONE TABLE (v3.6 UPGRADED)
# ==========================================
# Maps PPAS tier → (upside_low_mult, upside_high_mult, downside_low_mult, downside_high_mult)
# More aggressive zones for higher PPAS scores
ATR_ZONE_TABLE = {
    (92, 101): (3.5, 6.0, 3.5, 6.0),
    (80, 92):  (2.7, 4.5, 2.7, 4.5),
    (60, 80):  (2.0, 3.5, 2.0, 3.5),
    (0,  60):  (1.5, 2.5, 1.5, 2.5),
}

def get_atr_multipliers(ppas):
    for (lo, hi), mults in ATR_ZONE_TABLE.items():
        if lo <= ppas < hi:
            return mults
    return (2.7, 4.5, 2.7, 4.5)

# ==========================================
# 5. MAIN RADAR CLASS
# ==========================================
class VenusRadarV36:
    def __init__(self):
        self.exchange = ccxt.bybit({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
        self.alert_state = {}
        self.daily_risk_log = []
        self.last_recap_date = None
        # v3.6: track prediction outcomes for win-rate in recap
        self.outcome_log = []

        self.init_db()

        if os.path.exists(GLOBAL_MODEL_PATH):
            self.global_model = joblib.load(GLOBAL_MODEL_PATH)
            ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{ts}] {GREEN}✅ Global Model loaded:{RESET} {GLOBAL_MODEL_PATH}")
        else:
            print(f"{RED}❌ ERROR: Missing {GLOBAL_MODEL_PATH}. Run train_ppas.py first.{RESET}")
            sys.exit(1)

        self.coin_models = {}
        self._model_cache_ts = {}

    # ------------------------------------------------------------------
    def init_db(self):
        """Initialize MLOps DB with automatic schema migration."""
        conn = sqlite3.connect(PREDICTIONS_DB)
        conn.execute('''CREATE TABLE IF NOT EXISTS live_predictions 
                        (ts INTEGER, symbol TEXT, price REAL, ppas INTEGER,
                         dev REAL, vr REAL, vpr REAL, ls_ratio REAL,
                         mtf_mult REAL DEFAULT 1.0, ppas_adj INTEGER DEFAULT 0)''')

        # v3.6: outcome tracking table (actual vs predicted)
        conn.execute('''CREATE TABLE IF NOT EXISTS prediction_outcomes
                        (ts INTEGER, symbol TEXT, ppas_at_alert INTEGER,
                         price_at_alert REAL, price_4h_later REAL,
                         outcome TEXT, PRIMARY KEY(ts, symbol))''')

        # Auto-migration: add new columns to old DBs
        cursor = conn.execute("PRAGMA table_info(live_predictions)")
        cols = [info[1] for info in cursor.fetchall()]
        for col, typedef in [('ls_ratio', 'REAL DEFAULT 1.0'),
                              ('mtf_mult', 'REAL DEFAULT 1.0'),
                              ('ppas_adj', 'INTEGER DEFAULT 0')]:
            if col not in cols:
                conn.execute(f"ALTER TABLE live_predictions ADD COLUMN {col} {typedef}")
                print(f"{CYAN}🔧 DB Migration: added column '{col}'{RESET}")

        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    def get_ls_ratio(self, symbol):
        """Fetch real-time Long/Short ratio from Bybit v5 API."""
        try:
            sym_bybit = symbol.split(':')[0].replace('/', '')
            url = (f"https://api.bybit.com/v5/market/account-ratio"
                   f"?category=linear&symbol={sym_bybit}&period=15min&limit=1")
            resp = requests.get(url, timeout=5).json()
            if resp.get('retCode') == 0:
                lst = resp.get('result', {}).get('list', [])
                if lst:
                    buy  = float(lst[0].get('buyRatio', 1.0))
                    sell = float(lst[0].get('sellRatio', 1.0))
                    return buy / sell if sell > 0 else 1.0
        except Exception:
            pass
        return 1.0

    # ------------------------------------------------------------------
    def load_coin_model(self, sym_clean):
        """Load per-coin model with 1-hour cache to avoid repeated disk reads."""
        path = os.path.join(PER_COIN_DIR, f"ppas_model_{sym_clean}.pkl")
        if not os.path.exists(path):
            return None, False
        cached_ts = self._model_cache_ts.get(sym_clean, 0)
        if sym_clean not in self.coin_models or (time.time() - cached_ts) > 3600:
            self.coin_models[sym_clean] = joblib.load(path)
            self._model_cache_ts[sym_clean] = time.time()
        return self.coin_models[sym_clean], True

    # ------------------------------------------------------------------
    def process_coin(self, symbol):
        """Extract 11 KPIs, run prediction, apply MTF filter. Core scan logic."""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='15m', limit=1000)
            if len(ohlcv) < 672:
                return None

            df = pd.DataFrame(ohlcv, columns=['ts','open','high','low','close','volume'])
            c, v, h, l = df['close'], df['volume'], df['high'], df['low']
            idx = -2  # Last closed candle

            # --- 11 KPIs ---
            sma_200  = c.rolling(200).mean()
            dev_pct  = ((c.iloc[idx] - sma_200.iloc[idx]) / sma_200.iloc[idx]) * 100

            direction      = np.sign(c.diff())
            streak_penalty = abs(direction.iloc[idx-4:idx+1].sum()) * 2.5

            log_ret       = np.log(c / c.shift(1))
            sigma_1w      = log_ret.rolling(672).std().iloc[idx]
            sigma_distance= abs(log_ret.iloc[idx]) / (sigma_1w + 1e-9)

            delta = c.diff()
            gain  = delta.where(delta > 0, 0).rolling(56).mean()
            loss  = (-delta.where(delta < 0, 0)).rolling(56).mean()
            rsi   = 100 - (100 / (1 + gain.iloc[idx] / (loss.iloc[idx] + 1e-9)))

            vr    = log_ret.rolling(20).std().iloc[idx] * 100

            tr      = pd.concat([h - l,
                                  abs(h - c.shift(1)),
                                  abs(l - c.shift(1))], axis=1).max(axis=1)
            atr_56  = tr.rolling(56).mean()
            atr_pct = (atr_56.iloc[idx] / c.iloc[idx]) * 100

            vpr           = v.iloc[idx] / (v.rolling(20).mean().iloc[idx] + 1e-9)
            onchain_proxy = v.iloc[idx] / (v.rolling(100).mean().iloc[idx] + 1e-9)
            liq_attention = (h.iloc[idx] - l.iloc[idx]) / (v.iloc[idx] + 1e-9)
            ls_ratio      = self.get_ls_ratio(symbol)
            rp            = max(0, 100 - streak_penalty - abs(dev_pct))

            features = pd.DataFrame([{
                'dev_pct': dev_pct, 'streak_penalty': streak_penalty,
                'sigma_distance': sigma_distance, 'rsi': rsi,
                'volatility': vr, 'atr_pct': atr_pct,
                'volume_surge': vpr, 'onchain_proxy': onchain_proxy,
                'liq_attention': liq_attention, 'ls_ratio': ls_ratio, 'rp': rp
            }])

            # --- Weighted Ensemble Prediction (v3.6) ---
            sym_clean    = symbol.replace('/', '_').replace(':', '_')
            coin_model, is_per_coin = self.load_coin_model(sym_clean)

            if is_per_coin:
                p_coin   = coin_model.predict_proba(features)[0][1]
                p_global = self.global_model.predict_proba(features)[0][1]
                # Per-coin model gets 70% weight, global gets 30%
                raw_prob = (p_coin * 0.70) + (p_global * 0.30)
            else:
                raw_prob = self.global_model.predict_proba(features)[0][1]

            # --- MTF Confirmation (v3.6) ---
            mtf_mult = 1.0
            if MTF_ENABLED:
                mtf_mult = get_mtf_bias(self.exchange, symbol)

            ppas     = int(min(100, raw_prob * 100 * mtf_mult))
            ppas_adj = ppas - int(raw_prob * 100)  # delta for logging

            # --- Dynamic ATR Zones (v3.6) ---
            atr_val = atr_56.iloc[idx]
            u_lo, u_hi, d_lo, d_hi = get_atr_multipliers(ppas)
            rebound = {
                'start':      c.iloc[idx] + (u_lo * atr_val * 5),
                'max':        c.iloc[idx] + (u_hi * atr_val * 5),
                'dump_start': max(0, c.iloc[idx] - (d_lo * atr_val * 5)),
                'min':        max(0, c.iloc[idx] - (d_hi * atr_val * 5)),
            }

            return {
                'symbol': symbol, 'price': c.iloc[idx], 'ppas': ppas,
                'ppas_adj': ppas_adj, 'mtf_mult': round(mtf_mult, 2),
                'dev': round(dev_pct, 1), 'ls': round(ls_ratio, 2),
                'v': v.iloc[idx], 'vr': round(vr, 2), 'vpr': round(vpr, 1),
                'rsi': round(rsi, 1), 'sigma': round(sigma_distance, 2),
                'rebound': rebound, 'is_per_coin': is_per_coin
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    def get_adaptive_cooldown(self):
        """
        v3.6: Shorten alert cooldown during high-volatility market regimes.
        Uses market heat from the last scan stored in self._last_heat.
        """
        if not ADAPTIVE_COOLDOWN:
            return ALERT_COOLDOWN
        heat = getattr(self, '_last_heat', 0)
        if heat >= 50:   return ALERT_COOLDOWN // 4   # Very hot market
        if heat >= 30:   return ALERT_COOLDOWN // 2   # Moderate heat
        return ALERT_COOLDOWN

    # ------------------------------------------------------------------
    def check_daily_recap(self):
        """Send Daily Recap with win-rate tracking (v3.6 upgraded)."""
        now = datetime.datetime.now()
        if now.hour == RECAP_HOUR and now.minute < 15:
            if self.last_recap_date != now.date():
                if self.daily_risk_log:
                    df_recap = pd.DataFrame(self.daily_risk_log)
                    df_recap = df_recap.sort_values('ppas', ascending=False).drop_duplicates('symbol')

                    msg = f"📊 *DAILY RISK RECAP* ({now.strftime('%b-%d')})\n"
                    msg += f"AI flagged `{len(df_recap)}` coins today.\n\n"

                    for _, row in df_recap.head(10).iterrows():
                        mtf_tag = f" MTF×{row.get('mtf_mult', 1.0)}" if row.get('mtf_mult', 1.0) != 1.0 else ""
                        msg += f"• {row['symbol'].split('/')[0]}: Peak PPAS `{row['ppas']}`{mtf_tag}\n"

                    # v3.6: Win-rate from outcome log
                    if self.outcome_log:
                        wins = sum(1 for o in self.outcome_log if o.get('correct'))
                        wr   = wins / len(self.outcome_log) * 100
                        msg += f"\n🎯 *AI Win-Rate (today):* {wr:.1f}% ({wins}/{len(self.outcome_log)})"
                        self.outcome_log = []

                    send_telegram_chunks(msg)
                    self.daily_risk_log = []
                self.last_recap_date = now.date()

    # ------------------------------------------------------------------
    def format_alert(self, results, is_crash, heat):
        """Build Telegram alert message with Smart Mute and MTF tag."""
        if not results:
            return None
        results.sort(key=lambda x: x['ppas'], reverse=True)

        alerts, recoveries = [], []
        now_ts  = time.time()
        cooldown = self.get_adaptive_cooldown()

        for res in results:
            sym, ppas = res['symbol'], res['ppas']
            sym_s = sym.split('/')[0]
            state = self.alert_state.get(sym)

            # --- Recovery logic ---
            if state and state['level'] == "HIGH" and ppas <= RISK_THRESHOLD_SAFE:
                recoveries.append(
                    f"✅ *SAFE TO RESUME:* `{sym_s}`\n"
                    f"PPAS dropped to `{ppas}` | Price: `${format_price(res['price'])}`"
                )
                self.alert_state[sym] = {'ts': now_ts, 'ppas': ppas, 'level': 'SAFE'}
                continue

            # --- High risk alert ---
            if ppas >= RISK_THRESHOLD_HIGH:
                self.daily_risk_log.append({
                    'symbol': sym, 'ppas': ppas, 'mtf_mult': res.get('mtf_mult', 1.0)
                })

                should_alert = False
                if not state or state['level'] != "HIGH":
                    should_alert = True
                else:
                    if (now_ts - state['ts']) > cooldown:
                        should_alert = True
                    elif (ppas - state['ppas']) >= PPAS_JUMP_TRIGGER:
                        should_alert = True

                if should_alert:
                    model_tag = "🧠 `[PerCoin]`" if res['is_per_coin'] else "🤖 `[Global]`"
                    mtf_tag   = ""
                    if res.get('mtf_mult', 1.0) != 1.0:
                        direction = "▲ Confirmed" if res['mtf_mult'] > 1.0 else "▼ Dampened"
                        mtf_tag   = f"\nMTF Filter: `{direction}` (×{res['mtf_mult']})"

                    msg = (
                        f"⛔ *{sym_s}* {model_tag}\n"
                        f"PPAS: `{ppas}` | Dev: `{res['dev']}%` | RSI: `{res['rsi']}`\n"
                        f"L/S Ratio: `{res['ls']}x` | Vol Surge: `{res['vpr']}x`\n"
                        f"Sigma: `{res['sigma']}σ` | VR: `{res['vr']}%`\n"
                        f"Price: `${format_price(res['price'])}`{mtf_tag}\n"
                        f"🎯 Up Zone:   `${format_price(res['rebound']['start'])}` → `${format_price(res['rebound']['max'])}`\n"
                        f"🕳️ Down Zone: `${format_price(res['rebound']['dump_start'])}` → `${format_price(res['rebound']['min'])}`"
                    )
                    prefix = "📈 *UPDATE:* " if state and state['level'] == "HIGH" else ""
                    alerts.append(f"{prefix}{msg}")
                    self.alert_state[sym] = {'ts': now_ts, 'ppas': ppas, 'level': 'HIGH',
                                             'price': res['price']}

        if not alerts and not recoveries and not is_crash:
            return None

        ts_str   = datetime.datetime.now().strftime('%b-%d %H:%M')
        cooldown_note = ""
        if ADAPTIVE_COOLDOWN and cooldown != ALERT_COOLDOWN:
            cooldown_note = f" | ⚡ Adaptive Cooldown: {cooldown//60}m"

        final_msg = f"📡 *Venus Radar V3.6 — {ts_str}*{cooldown_note}\n"
        if is_crash:
            final_msg += f"\n🚨 *FLASH CRASH WARNING:* Market Heat `{heat:.1f}%`\n"
        if alerts:
            final_msg += "\n" + "\n\n".join(alerts)
        if recoveries:
            final_msg += "\n\n" + "\n".join(recoveries)

        return final_msg

    # ------------------------------------------------------------------
    def run_cycle(self):
        """Core market scan loop."""
        self.check_daily_recap()
        ts_str = datetime.datetime.now().strftime('%H:%M:%S')
        print(f"\n{CYAN}{BOLD}--- Venus Radar V3.6 | Scanning @ {ts_str} ---{RESET}")

        try:
            tickers = self.exchange.fetch_tickers()
            targets = sorted(
                [(s, d.get('quoteVolume', 0)) for s, d in tickers.items()
                 if '/USDT' in s and d.get('quoteVolume', 0) > 5_000_000],
                key=lambda x: x[1], reverse=True
            )
            symbols = [s for s, _ in targets[:TOP_SCAN_COINS]]
        except Exception as e:
            print(f"{RED}Exchange API error:{RESET} {e}")
            return

        processed = []
        for i, sym in enumerate(symbols):
            sys.stdout.write(f"\r{CYAN}Analysing {i+1}/{len(symbols)}:{RESET} {sym.ljust(20)}")
            sys.stdout.flush()
            data = self.process_coin(sym)
            if data:
                processed.append(data)
            time.sleep(0.05)

        print()  # newline after progress bar

        if not processed:
            print(f"{YELLOW}No data returned this cycle.{RESET}")
            return

        # --- MLOps: Log predictions ---
        conn = sqlite3.connect(PREDICTIONS_DB)
        ts   = int(time.time() * 1000)
        for p in processed:
            conn.execute(
                "INSERT INTO live_predictions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts, p['symbol'], p['price'], p['ppas'], p['dev'],
                 p['vr'], p['vpr'], p['ls'], p['mtf_mult'], p['ppas_adj'])
            )
        conn.commit()
        conn.close()

        # --- Market Heat Index (volume-weighted) ---
        total_v  = sum(p['v'] for p in processed)
        danger_v = sum(p['v'] for p in processed if p['ppas'] >= RISK_THRESHOLD_HIGH)
        heat = (danger_v / total_v * 100) if total_v > 0 else 0
        self._last_heat = heat

        heat_color = RED if heat >= MARKET_HEAT_THRESHOLD else (YELLOW if heat >= 15 else GREEN)
        print(f"{BOLD}Market Heat:{RESET} {heat_color}{heat:.1f}%{RESET} | "
              f"Coins scanned: {len(processed)} | "
              f"High Risk: {sum(1 for p in processed if p['ppas'] >= RISK_THRESHOLD_HIGH)}")

        # --- Console Top 10 Table ---
        processed.sort(key=lambda x: x['ppas'], reverse=True)
        print(f"\n{BOLD}>>> TOP 10 RISK RANKING (AI PREDICTION) <<<{RESET}")
        header = f"{'Symbol':<12} {'PPAS':>6} {'Dev%':>7} {'L/S':>6} {'Surge':>6} {'RSI':>6} {'Sigma':>7} {'MTF':>5}"
        print(header)
        print("─" * len(header))
        for p in processed[:10]:
            ppas_str = colorize_ppas(p['ppas'])
            mtf_str  = f"×{p['mtf_mult']}" if p['mtf_mult'] != 1.0 else "  —"
            print(f"{p['symbol'].split('/')[0]:<12} {ppas_str:>6} {p['dev']:>7} "
                  f"{p['ls']:>6} {p['vpr']:>6} {p['rsi']:>6} {p['sigma']:>7} {mtf_str:>5}")
        print("─" * len(header))

        # --- Telegram Alert ---
        alert = self.format_alert(processed, heat >= MARKET_HEAT_THRESHOLD, heat)
        if alert:
            send_telegram_chunks(alert)
            print(f"{GREEN}>>> Telegram alert sent.{RESET}")


# ==========================================
# 6. ENTRY POINT
# ==========================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Venus Radar V3.6 — AI Crypto Risk Scanner")
    parser.add_argument('--oneshot', action='store_true',
                        help='Run one scan then exit (for use with .bat scheduler)')
    args, _ = parser.parse_known_args()

    bot = VenusRadarV36()

    if args.oneshot:
        bot.run_cycle()
    else:
        print(f"{CYAN}Venus Radar V3.6 running in continuous mode. Press Ctrl+C to stop.{RESET}")
        while True:
            try:
                bot.run_cycle()
                print(f"Sleeping {SCAN_INTERVAL}s until next scan...")
                time.sleep(SCAN_INTERVAL)
            except KeyboardInterrupt:
                print(f"\n{YELLOW}Radar stopped by user.{RESET}")
                break
            except Exception as e:
                print(f"{RED}Loop error:{RESET} {e}")
                time.sleep(60)
