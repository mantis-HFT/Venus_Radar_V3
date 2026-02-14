"""
PDRS Venus Radar V2 - Real-time Risk Scanner for Crypto Futures
Detects potential reversal/overextension risk in crypto perpetual futures
"""

import ccxt
import pandas as pd
import numpy as np
import sqlite3
import time
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple
import requests
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class AlertConfig:
    """Configuration for alert thresholds"""
    HIGH_RISK_PPAS: int = 85
    POTENTIAL_RISK_PPAS: int = 75
    HIGH_DEVIATION_THRESHOLD: float = 15.0  # %
    MEDIUM_DEVIATION_THRESHOLD: float = 10.0  # %
    VERY_LOW_RP_THRESHOLD: int = 30
    LOW_RP_THRESHOLD: int = 50
    
    # Telegram settings
    TELEGRAM_ENABLED: bool = False
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""


class VenusRadarDB:
    """Handles database operations for Venus Radar"""
    
    def __init__(self, db_path: str = "pdrs_venus_radar_v2.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Alerts history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                ppas_score REAL,
                alert_level TEXT,
                deviation REAL,
                rp_score REAL,
                exchange TEXT
            )
        """)
        
        # Price data cache table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_cache (
                symbol TEXT,
                exchange TEXT,
                timeframe TEXT,
                timestamp INTEGER,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY (symbol, exchange, timeframe, timestamp)
            )
        """)
        
        # Coin rankings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coin_rankings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT,
                ppas_score REAL,
                deviation REAL,
                rp_score REAL,
                volume_24h REAL,
                exchange TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized: {self.db_path}")
    
    def log_alert(self, symbol: str, ppas: float, level: str, 
                  deviation: float, rp: float, exchange: str):
        """Log an alert to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alerts_history (symbol, ppas_score, alert_level, deviation, rp_score, exchange)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symbol, ppas, level, deviation, rp, exchange))
        conn.commit()
        conn.close()
    
    def get_recent_alerts(self, symbol: str, hours: int = 2) -> List[Dict]:
        """Get recent alerts for a symbol"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cutoff = datetime.now() - timedelta(hours=hours)
        cursor.execute("""
            SELECT * FROM alerts_history 
            WHERE symbol = ? AND timestamp > ?
            ORDER BY timestamp DESC
        """, (symbol, cutoff))
        results = cursor.fetchall()
        conn.close()
        return results
    
    def save_ranking(self, symbol: str, ppas: float, deviation: float, 
                     rp: float, volume: float, exchange: str):
        """Save coin ranking"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO coin_rankings (symbol, ppas_score, deviation, rp_score, volume_24h, exchange)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symbol, ppas, deviation, rp, volume, exchange))
        conn.commit()
        conn.close()


class VenusRadar:
    """Main Venus Radar scanner class"""
    
    def __init__(self, config: AlertConfig = None):
        self.config = config or AlertConfig()
        self.db = VenusRadarDB()
        
        # Initialize exchanges
        try:
            self.bybit = ccxt.bybit({
                'enableRateLimit': True,
                'options': {'defaultType': 'linear'}
            })
            logger.info("Bybit client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Bybit: {e}")
            self.bybit = None
        
        try:
            self.binance = ccxt.binance({
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
            logger.info("Binance client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Binance: {e}")
            self.binance = None
    
    def get_top_100_futures(self, exchange_name: str = 'bybit') -> List[Dict]:
        """Get top 100 futures by volume"""
        try:
            exchange = self.bybit if exchange_name == 'bybit' else self.binance
            if not exchange:
                return []
            
            tickers = exchange.fetch_tickers()
            
            # Filter USDT pairs with reasonable volume
            filtered = []
            for symbol, ticker in tickers.items():
                if 'USDT' in symbol and ticker.get('quoteVolume', 0) > 0:
                    filtered.append({
                        'symbol': symbol,
                        'volume': ticker.get('quoteVolume', 0),
                        'price': ticker.get('last', 0)
                    })
            
            # Sort by volume and take top 100
            filtered.sort(key=lambda x: x['volume'], reverse=True)
            return filtered[:100]
            
        except Exception as e:
            logger.error(f"Error fetching top futures: {e}")
            return []
    
    def get_smart_filtered_coins(self, top_coins: List[Dict], 
                                 exchange_name: str = 'bybit') -> List[str]:
        """Filter to top gainers and losers based on 24h change"""
        try:
            exchange = self.bybit if exchange_name == 'bybit' else self.binance
            if not exchange:
                return []
            
            changes = []
            for coin in top_coins:
                try:
                    symbol = coin['symbol']
                    # Fetch 1d candles for 24h change
                    candles = exchange.fetch_ohlcv(symbol, '1d', limit=2)
                    if len(candles) >= 2:
                        old_price = candles[-2][4]  # Previous close
                        new_price = candles[-1][4]  # Current close
                        change_pct = ((new_price - old_price) / old_price) * 100
                        changes.append({
                            'symbol': symbol,
                            'change': change_pct
                        })
                except Exception as e:
                    logger.debug(f"Could not get 24h change for {coin['symbol']}: {e}")
                    continue
            
            # Sort by change
            changes.sort(key=lambda x: x['change'], reverse=True)
            
            # Top 30 gainers + Top 10 losers
            top_gainers = [c['symbol'] for c in changes[:30]]
            top_losers = [c['symbol'] for c in changes[-10:]]
            
            result = list(set(top_gainers + top_losers))
            logger.info(f"Filtered to {len(result)} coins for analysis")
            return result
            
        except Exception as e:
            logger.error(f"Error in smart filtering: {e}")
            return []
    
    def calculate_ppas(self, df: pd.DataFrame, window_hours: int = 4) -> Dict:
        """
        Calculate PPAS (Potential Pump Alert Score) for a given window
        Returns dict with score and components
        """
        try:
            if len(df) < window_hours:
                return None
            
            # Work with the most recent window
            window_df = df.tail(window_hours * 2)  # Get extra data for context
            recent_df = window_df.tail(window_hours)
            
            if len(recent_df) < 4:
                return None
            
            # Calculate components
            components = {}
            
            # 1. Volatility (n_vr) - annualized from log returns
            log_returns = np.log(recent_df['close'] / recent_df['close'].shift(1)).dropna()
            if len(log_returns) > 1:
                volatility = log_returns.std() * np.sqrt(24 * 365)  # Annualized for hourly
                n_vr = min(volatility * 100, 100)  # Normalize
            else:
                n_vr = 0
            components['n_vr'] = n_vr
            
            # 2. LAF (Liquidity Attention Factor) - FIXED for now
            n_laf = 80
            components['n_laf'] = n_laf
            
            # 3. SCI (Social/Community Interest) - FIXED for now  
            n_sci = 75
            components['n_sci'] = n_sci
            
            # 4. HMS (High Momentum Spike) - recent volume vs average
            avg_volume = window_df['volume'].mean()
            recent_volume = recent_df.tail(4)['volume'].mean()
            if avg_volume > 0:
                n_hms = min((recent_volume / avg_volume) * 50, 100)
            else:
                n_hms = 0
            components['n_hms'] = n_hms
            
            # 5. LVR (Largest Volume Ratio) - biggest spike
            if avg_volume > 0:
                max_volume = recent_df['volume'].max()
                n_lvr = min((max_volume / avg_volume) * 50, 100)
            else:
                n_lvr = 0
            components['n_lvr'] = n_lvr
            
            # 6. SBR (Short-term Burst Ratio) - recent 1h vs overall
            if len(df) > window_hours:
                overall_avg = df['volume'].mean()
                last_hour_vol = recent_df.tail(1)['volume'].iloc[0]
                if overall_avg > 0:
                    n_sbr = min((last_hour_vol / overall_avg) * 50, 100)
                else:
                    n_sbr = 0
            else:
                n_sbr = 0
            components['n_sbr'] = n_sbr
            
            # 7. VPR (Volume Pattern Ratio) - short vs long term
            if len(df) > window_hours * 2:
                short_avg = recent_df['volume'].mean()
                long_avg = df.tail(window_hours * 4)['volume'].mean()
                if long_avg > 0:
                    n_vpr = min((short_avg / long_avg) * 50, 100)
                else:
                    n_vpr = 0
            else:
                n_vpr = 0
            components['n_vpr'] = n_vpr
            
            # 8. TAMS (Technical Analysis Momentum Score)
            # Simple RSI + price vs SMA
            closes = recent_df['close']
            delta = closes.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=min(14, len(closes))).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=min(14, len(closes))).mean()
            rs = gain / loss.replace(0, 1)
            rsi = 100 - (100 / (1 + rs))
            rsi_val = rsi.iloc[-1] if not rsi.empty else 50
            
            # SMA comparison
            sma = closes.mean()
            current_price = closes.iloc[-1]
            above_sma = 1 if current_price > sma else 0
            
            # Combine (normalized)
            n_tams = (rsi_val * 0.6) + (above_sma * 40)
            components['n_tams'] = min(n_tams, 100)
            
            # 9. OCAI (On-Chain Activity Indicator) - proxy via volume
            if avg_volume > 0:
                n_ocai = min((recent_df['volume'].max() / avg_volume) * 30, 100)
            else:
                n_ocai = 0
            components['n_ocai'] = n_ocai
            
            # 10. RP (Reversal Potential) - streak + deviation penalty
            # Calculate price streak
            price_changes = recent_df['close'].diff().dropna()
            if len(price_changes) > 0:
                current_direction = 1 if price_changes.iloc[-1] > 0 else -1
                streak = 0
                for change in reversed(price_changes.tolist()):
                    if (change > 0 and current_direction == 1) or (change < 0 and current_direction == -1):
                        streak += 1
                    else:
                        break
                streak_penalty = min(streak * 5, 30)
            else:
                streak_penalty = 0
            
            # Calculate deviation from moving average
            avg_price = window_df['close'].mean()
            current_price = recent_df['close'].iloc[-1]
            deviation_pct = abs((current_price - avg_price) / avg_price) * 100
            deviation_penalty = min(deviation_pct * 2, 40)
            
            rp = max(100 - streak_penalty - deviation_penalty, 0)
            components['rp'] = rp
            components['deviation_pct'] = deviation_pct
            components['streak'] = streak if 'streak' in locals() else 0
            
            # Calculate weighted PPAS
            weights = {
                'n_vr': 0.15,
                'n_laf': 0.15,
                'n_sci': 0.15,
                'n_hms': 0.10,
                'n_lvr': 0.10,
                'n_sbr': 0.15,
                'n_vpr': 0.10,
                'n_tams': 0.10,
                'n_ocai': 0.10,
                'rp': 0.15
            }
            
            # But we actually want LOW rp to increase risk, so invert it
            ppas = (
                weights['n_vr'] * n_vr +
                weights['n_laf'] * n_laf +
                weights['n_sci'] * n_sci +
                weights['n_hms'] * n_hms +
                weights['n_lvr'] * n_lvr +
                weights['n_sbr'] * n_sbr +
                weights['n_vpr'] * n_vpr +
                weights['n_tams'] * n_tams +
                weights['n_ocai'] * n_ocai +
                weights['rp'] * (100 - rp)  # Invert RP - low RP = high risk
            )
            
            # Temporary boost (as per original spec)
            ppas = min(ppas * 1.8, 100)
            
            return {
                'ppas': ppas,
                'components': components,
                'deviation_pct': deviation_pct,
                'rp': rp
            }
            
        except Exception as e:
            logger.error(f"Error calculating PPAS: {e}")
            return None
    
    def process_single_coin(self, symbol: str, exchange_name: str = 'bybit') -> Optional[Dict]:
        """Process a single coin and return its analysis"""
        try:
            exchange = self.bybit if exchange_name == 'bybit' else self.binance
            if not exchange:
                return None
            
            # Fetch hourly candles
            candles = exchange.fetch_ohlcv(symbol, '1h', limit=200)
            
            if len(candles) < 4:
                logger.debug(f"Not enough data for {symbol}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Calculate PPAS for different windows
            windows = [4, 2, 1]  # hours
            results = []
            
            for window in windows:
                result = self.calculate_ppas(df, window)
                if result:
                    result['window'] = window
                    results.append(result)
            
            if not results:
                return None
            
            # Take the highest PPAS (worst case)
            best_result = max(results, key=lambda x: x['ppas'])
            
            # Check for recent alerts
            recent_alerts = self.db.get_recent_alerts(symbol, hours=2)
            is_repeat = len(recent_alerts) > 0
            
            # Get 24h volume
            ticker = exchange.fetch_ticker(symbol)
            volume_24h = ticker.get('quoteVolume', 0)
            
            return {
                'symbol': symbol,
                'ppas': best_result['ppas'],
                'deviation': best_result['deviation_pct'],
                'rp': best_result['rp'],
                'components': best_result['components'],
                'window': best_result['window'],
                'is_repeat': is_repeat,
                'volume_24h': volume_24h,
                'exchange': exchange_name
            }
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
            return None
    
    def send_telegram_alert(self, message: str):
        """Send alert via Telegram"""
        if not self.config.TELEGRAM_ENABLED:
            return
        
        try:
            url = f"https://api.telegram.org/bot{self.config.TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {
                'chat_id': self.config.TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=data, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram alert sent successfully")
            else:
                logger.error(f"Telegram alert failed: {response.text}")
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
    
    def run_scan(self, exchange_name: str = 'bybit'):
        """Run a single scan cycle"""
        logger.info("=" * 80)
        logger.info(f"Starting Venus Radar scan - {datetime.now()}")
        logger.info("=" * 80)
        
        # Step 1: Get top 100 by volume
        logger.info("Fetching top 100 futures by volume...")
        top_100 = self.get_top_100_futures(exchange_name)
        
        if not top_100:
            logger.warning("No coins fetched, skipping scan")
            return
        
        logger.info(f"Found {len(top_100)} coins")
        
        # Step 2: Smart filter to ~40 coins
        logger.info("Applying smart filter (top gainers + losers)...")
        filtered_symbols = self.get_smart_filtered_coins(top_100, exchange_name)
        
        if not filtered_symbols:
            logger.warning("No coins passed filter, skipping scan")
            return
        
        logger.info(f"Analyzing {len(filtered_symbols)} filtered coins...")
        
        # Step 3: Process coins in parallel
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self.process_single_coin, symbol, exchange_name): symbol 
                for symbol in filtered_symbols
            }
            
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error processing {symbol}: {e}")
        
        if not results:
            logger.warning("No valid results from scan")
            return
        
        # Step 4: Sort by PPAS
        results.sort(key=lambda x: x['ppas'], reverse=True)
        
        # Step 5: Generate alerts
        alerts = []
        
        for result in results:
            symbol = result['symbol']
            ppas = result['ppas']
            deviation = result['deviation']
            rp = result['rp']
            
            # Determine alert level
            alert_level = None
            
            if ppas >= self.config.HIGH_RISK_PPAS:
                alert_level = "HIGH RISK"
            elif ppas >= self.config.POTENTIAL_RISK_PPAS:
                alert_level = "POTENTIAL RISK"
            elif deviation >= self.config.HIGH_DEVIATION_THRESHOLD and rp < self.config.VERY_LOW_RP_THRESHOLD:
                alert_level = "HIGH RISK"
            elif deviation >= self.config.MEDIUM_DEVIATION_THRESHOLD and rp < self.config.LOW_RP_THRESHOLD:
                alert_level = "POTENTIAL RISK"
            
            if alert_level:
                alerts.append({
                    'symbol': symbol,
                    'level': alert_level,
                    'ppas': ppas,
                    'deviation': deviation,
                    'rp': rp,
                    'volume_24h': result['volume_24h'],
                    'is_repeat': result['is_repeat']
                })
                
                # Log to database
                self.db.log_alert(symbol, ppas, alert_level, deviation, rp, result['exchange'])
            
            # Save ranking
            self.db.save_ranking(
                symbol, ppas, deviation, rp, 
                result['volume_24h'], result['exchange']
            )
        
        # Step 6: Display results
        logger.info("\n" + "=" * 80)
        logger.info("TOP 10 COINS BY PPAS SCORE")
        logger.info("=" * 80)
        
        for i, result in enumerate(results[:10], 1):
            logger.info(f"\n{i}. {result['symbol']}")
            logger.info(f"   PPAS: {result['ppas']:.2f}")
            logger.info(f"   Deviation: {result['deviation']:.2f}%")
            logger.info(f"   RP Score: {result['rp']:.2f}")
            logger.info(f"   24h Volume: ${result['volume_24h']:,.0f}")
            logger.info(f"   Window: {result['window']}h")
        
        # Step 7: Send alerts
        if alerts:
            logger.info("\n" + "=" * 80)
            logger.info(f"⚠️  {len(alerts)} ALERTS GENERATED")
            logger.info("=" * 80)
            
            alert_message = f"🚨 <b>Venus Radar Alert</b> 🚨\n\n"
            alert_message += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            alert_message += f"Exchange: {exchange_name.upper()}\n\n"
            
            for alert in alerts:
                repeat_flag = " [REPEAT]" if alert['is_repeat'] else ""
                logger.info(f"\n{alert['level']}: {alert['symbol']}{repeat_flag}")
                logger.info(f"   PPAS: {alert['ppas']:.2f}")
                logger.info(f"   Deviation: {alert['deviation']:.2f}%")
                logger.info(f"   RP: {alert['rp']:.2f}")
                
                alert_message += f"{alert['level']}: <b>{alert['symbol']}</b>{repeat_flag}\n"
                alert_message += f"PPAS: {alert['ppas']:.2f} | Dev: {alert['deviation']:.2f}% | RP: {alert['rp']:.2f}\n\n"
            
            self.send_telegram_alert(alert_message)
        else:
            logger.info("\nNo alerts generated this scan")
        
        logger.info("\n" + "=" * 80)
        logger.info(f"Scan completed at {datetime.now()}")
        logger.info("=" * 80)
    
    def run_loop(self, interval_minutes: int = 10, exchange_name: str = 'bybit'):
        """Run continuous scanning loop"""
        logger.info(f"Venus Radar V2 started - scanning every {interval_minutes} minutes")
        logger.info(f"Exchange: {exchange_name}")
        
        while True:
            try:
                self.run_scan(exchange_name)
            except Exception as e:
                logger.error(f"Error in scan loop: {e}", exc_info=True)
            
            logger.info(f"\nWaiting {interval_minutes} minutes until next scan...")
            time.sleep(interval_minutes * 60)


def main():
    """Main entry point"""
    # Configuration
    config = AlertConfig(
        HIGH_RISK_PPAS=85,
        POTENTIAL_RISK_PPAS=75,
        HIGH_DEVIATION_THRESHOLD=15.0,
        MEDIUM_DEVIATION_THRESHOLD=10.0,
        VERY_LOW_RP_THRESHOLD=30,
        LOW_RP_THRESHOLD=50,
        
        # Telegram (set to True and add credentials to enable)
        TELEGRAM_ENABLED=False,
        TELEGRAM_BOT_TOKEN="",  # Your bot token
        TELEGRAM_CHAT_ID=""     # Your chat ID
    )
    
    # Initialize and run
    radar = VenusRadar(config)
    
    # Choose exchange: 'bybit' or 'binance'
    exchange = 'bybit'
    
    # Run continuous loop (every 10 minutes)
    radar.run_loop(interval_minutes=10, exchange_name=exchange)


if __name__ == "__main__":
    main()
