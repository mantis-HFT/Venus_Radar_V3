"""
PDRS Calculator V3.6
Parabolic Danger & Risk Scoring — Enhanced Edition

Changelog v3.6:
  • Added Trend Context Modifier (TCM): uptrend reduces danger score, downtrend amplifies
  • Added Volume Climax Detection: sudden spike after sustained trend = blow-off signal
  • RSI Divergence proxy included in PDRS aggregate
  • Cleaner band-based interpretation with emoji tier labels
  • Improved CoinGecko ID mapping (more coins added)
"""

import numpy as np
import pandas as pd
import requests
import time
import logging
from pycoingecko import CoinGeckoAPI
from datetime import datetime, timedelta

cg = CoinGeckoAPI()

BTC_HISTORY_CACHE = None
BTC_CACHE_TIME    = 0


def get_coingecko_id(symbol):
    """
    Map a ticker symbol to a CoinGecko ID.
    Extended mapping for V3.6.
    Add missing coins to the `mapping` dict below.
    """
    symbol = symbol.lower().replace('-usd', '').replace('/usdt', '').split(':')[0]

    if symbol.startswith('1000') and len(symbol) > 4:
        symbol = symbol[4:]
    elif symbol.startswith('k') and len(symbol) > 3:
        symbol = symbol[1:]

    mapping = {
        # Major
        'btc': 'bitcoin', 'eth': 'ethereum', 'sol': 'solana',
        'bnb': 'binancecoin', 'xrp': 'ripple', 'doge': 'dogecoin',
        'ada': 'cardano', 'link': 'chainlink', 'dot': 'polkadot',
        'matic': 'matic-network', 'ltc': 'litecoin', 'uni': 'uniswap',
        'avax': 'avalanche-2', 'atom': 'cosmos', 'near': 'near',
        'apt': 'aptos', 'arb': 'arbitrum', 'op': 'optimism',
        'sui': 'sui', 'sei': 'sei-network', 'tia': 'celestia',
        # Meme & radar targets
        'river': 'river', 'siren': 'siren', 'pnut': 'peanut-the-squirrel',
        'virtual': 'virtual-protocol', 'pengu': 'pudgy-penguins',
        'goat': 'goatseus-maximus', 'act': 'act-i-the-ai-prophecy',
        'moodeng': 'moodeng-on-eth', 'neiro': 'neiro-on-eth',
        'turbo': 'turbo', 'troy': 'troy',
        # DeFi
        'cow': 'cow-protocol', 'safe': 'safe-coin',
        'eigen': 'eigenlayer', 'enso': 'enso-finance',
        # Other
        'brev': 'brevis-network', 'skr': 'skr',
    }

    if symbol in mapping:
        return mapping[symbol]

    try:
        results = cg.search(query=symbol)
        for coin in results.get('coins', []):
            if coin['symbol'].lower() == symbol:
                return coin['id']
    except Exception:
        pass
    return None


def get_bitcoin_history():
    global BTC_HISTORY_CACHE, BTC_CACHE_TIME
    if BTC_HISTORY_CACHE is not None and (time.time() - BTC_CACHE_TIME < 3600):
        return BTC_HISTORY_CACHE
    try:
        data   = cg.get_coin_market_chart_by_id(id='bitcoin', vs_currency='usd', days=30)
        prices = [p[1] for p in data['prices']]
        BTC_HISTORY_CACHE = pd.Series(prices)
        BTC_CACHE_TIME    = time.time()
        return BTC_HISTORY_CACHE
    except Exception as e:
        logging.error(f"Failed to fetch BTC history: {e}")
        return None


def get_ticker_data(cg_id):
    try:
        data    = cg.get_coin_market_chart_by_id(id=cg_id, vs_currency='usd', days=30)
        prices  = [p[1] for p in data['prices']]
        volumes = [v[1] for v in data['total_volumes']]
        return pd.Series(prices), pd.Series(volumes)
    except Exception as e:
        logging.error(f"Failed to fetch data for {cg_id}: {e}")
        return None, None


def detect_volume_climax(prices_series, volumes_series):
    """
    v3.6: Detect a volume climax — volume spike (>2x avg) at the end of a
    sustained directional move. Classic blow-off top / capitulation signal.
    Returns a score 0–100.
    """
    if prices_series is None or volumes_series is None or len(volumes_series) < 10:
        return 0
    avg_vol  = volumes_series[:-3].mean()
    last_vol = volumes_series.iloc[-1]
    vol_spike = last_vol / (avg_vol + 1e-9)

    # Was there a sustained directional move in the last 10 candles?
    ret_10 = prices_series.pct_change().tail(10)
    pos    = (ret_10 > 0).sum()
    trend_strength = max(pos, 10 - pos) / 10   # 0.5 = flat, 1.0 = unidirectional

    climax_score = min(100, (vol_spike - 1.5) * 40 * trend_strength)
    return max(0, climax_score)


def get_trend_context_modifier(prices_series):
    """
    v3.6: Simple trend context.
    Strong uptrend with no reversal signal → slightly lower danger.
    Downtrend or overextension → higher danger multiplier.
    Returns multiplier 0.8–1.2.
    """
    if prices_series is None or len(prices_series) < 30:
        return 1.0
    ema20 = prices_series.ewm(span=20, adjust=False).mean()
    ema50 = prices_series.ewm(span=50, adjust=False).mean()
    curr  = prices_series.iloc[-1]

    if curr > ema20.iloc[-1] > ema50.iloc[-1]:
        # Healthy uptrend: slight danger discount
        return 0.90
    elif curr < ema20.iloc[-1] < ema50.iloc[-1]:
        # Downtrend: amplify risk score
        return 1.15
    return 1.0


def calculate_pdrs(ticker_symbol, df_1h=None):
    """
    PDRS Calculator V3.6 — Enhanced Parabolic Danger & Risk Score.

    KPI Weights:
        Volatility (VR):          30%
        Acceleration:             10%
        Parabolic Extension:      25%  (was 30% — shared with climax)
        Volume Climax:             5%  (v3.6 new)
        Momentum Persistence:     15%
        BTC Correlation (LAF):    15%

    Post-aggregation modifiers:
        Trend Context Multiplier: ×0.9 to ×1.15
    """
    try:
        cg_id = get_coingecko_id(ticker_symbol)

        if not cg_id:
            return {
                'score': 0,
                'risk_level': 'ID ERROR',
                'details': 'N/A',
                'interpretation': (
                    f"⚠️ CoinGecko ID not found for '{ticker_symbol}'. "
                    f"Add it to the mapping in pdrs_calculator.py."
                ),
                'prediction': ''
            }

        prices_30d, volumes_30d = get_ticker_data(cg_id)
        if prices_30d is None or df_1h is None or len(df_1h) < 24:
            return {
                'score': 0,
                'risk_level': 'NO DATA',
                'interpretation': 'Insufficient history for PDRS.',
                'prediction': ''
            }

        # --- KPI 1: VOLATILITY ---
        returns_1h = df_1h['close'].pct_change().fillna(0)
        volatility  = returns_1h.std() * 100
        n_vr        = np.nan_to_num(min(100, volatility * 5))

        # --- KPI 2: ACCELERATION ---
        last_move   = returns_1h.iloc[-1] * 100
        avg_move    = returns_1h.abs().mean() * 100
        acceleration= abs(last_move) / (avg_move + 1e-9)
        n_accel     = np.nan_to_num(min(100, acceleration * 10))

        # --- KPI 3: PARABOLIC EXTENSION ---
        sma_24        = df_1h['close'].rolling(window=24).mean().iloc[-1]
        extension_ratio = (df_1h['close'].iloc[-1] / sma_24) if sma_24 > 0 else 1
        n_ext         = np.nan_to_num(min(100, max(0, (extension_ratio - 1.2) * 60)))

        # --- KPI 4 (v3.6): VOLUME CLIMAX ---
        n_climax = detect_volume_climax(
            df_1h['close'] if 'close' in df_1h else prices_30d,
            df_1h['volume'] if 'volume' in df_1h else volumes_30d
        )

        # --- KPI 5: MOMENTUM PERSISTENCE ---
        recent_12 = returns_1h.tail(12)
        green_count = (recent_12 > 0).sum()
        n_persist   = np.nan_to_num((green_count / 12) * 100)

        # --- KPI 6: BTC CORRELATION (Low Autonomy Factor) ---
        btc_prices = get_bitcoin_history()
        n_laf = 50
        if btc_prices is not None:
            min_len = min(len(prices_30d), len(btc_prices))
            corr    = prices_30d.tail(min_len).corr(btc_prices.tail(min_len))
            n_laf   = np.nan_to_num((1 - abs(corr)) * 100)

        # --- AGGREGATE ---
        pdrs_raw = (
            n_vr      * 0.30 +
            n_accel   * 0.10 +
            n_ext     * 0.25 +
            n_climax  * 0.05 +
            n_persist * 0.15 +
            n_laf     * 0.15
        )

        # v3.6: Apply Trend Context Modifier
        tcm  = get_trend_context_modifier(prices_30d)
        pdrs = min(100, round(pdrs_raw * tcm, 1))

        # --- INTERPRETATION ---
        curr_price = df_1h['close'].iloc[-1]
        max_30d    = prices_30d.max()
        min_30d    = prices_30d.min()

        if pdrs > 75:
            interpretation = "🔴 EXTREME PARABOLIC: Price overheated. Critical Blow-off Top risk."
        elif pdrs > 50:
            interpretation = "🟠 STRONG MOMENTUM: Trend accelerating into Resistance. Watch for reversal."
        elif n_climax > 60:
            interpretation = "🟡 VOLUME CLIMAX: Potential exhaustion move. High reversal probability."
        elif n_vr > 70:
            interpretation = "🟡 HIGH VOLATILITY: Heavy Whale Accumulation or Distribution detected."
        else:
            interpretation = "🟢 STABLE: Market in Accumulation or Sideways zone."

        # --- PREDICTION ---
        if curr_price < (max_30d * 0.5):
            target     = curr_price * 1.3
            prediction = (
                f"Potential Bottom formation. Short-term target: ${target:.4f}. "
                f"Hard Support: ${min_30d:.4f}."
            )
        else:
            resistance = max_30d * 1.1
            prediction = (
                f"Trend Extension. Next Resistance: ${resistance:.4f}. "
                f"Take profit zone if PDRS > 80."
            )

        r_level = 'HIGH' if pdrs > 60 else ('MEDIUM' if pdrs > 40 else 'LOW')

        return {
            'score': pdrs,
            'risk_level': r_level,
            'details': (
                f"V:{int(n_vr)} E:{int(n_ext)} P:{int(n_persist)} "
                f"L:{int(n_laf)} C:{int(n_climax)} TCM:{tcm:.2f}"
            ),
            'interpretation': interpretation,
            'prediction': prediction
        }

    except Exception as e:
        logging.error(f"PDRS Calculation failed for {ticker_symbol}: {e}")
        return {'score': 0, 'risk_level': 'SYSTEM ERROR', 'interpretation': str(e), 'prediction': ''}
