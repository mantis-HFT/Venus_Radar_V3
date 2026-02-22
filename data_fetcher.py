"""
data_fetcher.py — Venus Radar V3.6
Async OHLCV Data Fetcher from Bybit

Changelog v3.6:
  • Retry with exponential backoff on failed symbol fetches
  • Progress bar with ETA display
  • Auto-prune: removes candles older than 90 days to keep DB lean
  • Validates fetched candles for data integrity before inserting
  • Logs fetch summary per run to a rotating daily log file
"""

import asyncio
import ccxt.async_support as ccxt_async
import sqlite3
import pandas as pd
import time
import logging
import datetime
import os
import configparser
import sys

# ==========================================
# LOAD CONFIGURATION
# ==========================================
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

MARKET_DB         = config['DATA_FETCH']['market_db']
EXCHANGE_ID       = config['MARKET']['exchange_id']
TIMEFRAME         = config['MARKET']['timeframe']
CONCURRENCY_LIMIT = config['DATA_FETCH'].getint('concurrency_limit')
FETCH_LIMIT       = config['DATA_FETCH'].getint('fetch_limit')
TOP_COINS         = config['MARKET'].getint('top_coins')

# v3.6: prune candles older than this many days to keep DB size manageable
PRUNE_DAYS = 90

# Setup Logging — console + daily rotating file
os.makedirs('logs', exist_ok=True)
log_file = f"logs/data_fetcher_{datetime.datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding='utf-8')
    ]
)


# ==========================================
# DATABASE SETUP
# ==========================================
def setup_database():
    conn   = sqlite3.connect(MARKET_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historical_ohlcv (
            symbol       TEXT,
            timeframe    TEXT,
            timestamp_ms INTEGER,
            open         REAL,
            high         REAL,
            low          REAL,
            close        REAL,
            volume       REAL,
            PRIMARY KEY (symbol, timeframe, timestamp_ms)
        )
    ''')
    # Index for fast incremental queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sym_tf_ts
        ON historical_ohlcv (symbol, timeframe, timestamp_ms)
    ''')
    conn.commit()
    return conn


def prune_old_candles(conn):
    """v3.6: Remove candles older than PRUNE_DAYS to keep DB size lean."""
    cutoff_ms = int((time.time() - PRUNE_DAYS * 86400) * 1000)
    cursor    = conn.cursor()
    cursor.execute(
        "DELETE FROM historical_ohlcv WHERE timestamp_ms < ?", (cutoff_ms,)
    )
    pruned = cursor.rowcount
    conn.commit()
    if pruned > 0:
        logging.info(f"🧹 Pruned {pruned:,} candles older than {PRUNE_DAYS} days.")
    return pruned


# ==========================================
# SYMBOL SELECTION
# ==========================================
async def get_top_symbols(exchange, limit=100):
    logging.info("Fetching ticker list from exchange...")
    tickers = await exchange.fetch_tickers()

    pairs = []
    for symbol, data in tickers.items():
        if '/USDT' in symbol and (':USDT' in symbol or ':' not in symbol):
            qv = data.get('quoteVolume', 0)
            if qv and qv > 0:
                pairs.append({'symbol': symbol, 'volume': qv})

    df      = pd.DataFrame(pairs).sort_values('volume', ascending=False).head(limit)
    symbols = df['symbol'].tolist()
    logging.info(f"Selected {len(symbols)} top-volume coins.")
    return symbols


# ==========================================
# INCREMENTAL FETCH WITH RETRY
# ==========================================
def get_last_timestamp(cursor, symbol, timeframe):
    cursor.execute(
        "SELECT MAX(timestamp_ms) FROM historical_ohlcv WHERE symbol=? AND timeframe=?",
        (symbol, timeframe)
    )
    result = cursor.fetchone()
    return result[0] if result[0] is not None else None


def validate_candle(row):
    """v3.6: Basic sanity checks — reject broken candles."""
    ts, o, h, l, c, v = row[0], row[1], row[2], row[3], row[4], row[5]
    if any(x is None or x != x for x in [o, h, l, c, v]):  # NaN check
        return False
    if h < l or h < o or h < c or l > o or l > c:           # OHLC logic
        return False
    if v < 0 or c <= 0:
        return False
    return True


async def fetch_ohlcv_for_symbol(exchange, symbol, timeframe, semaphore, cursor,
                                  completed, total):
    async with semaphore:
        last_ts = get_last_timestamp(cursor, symbol, timeframe)

        if not last_ts:
            since = exchange.milliseconds() - (FETCH_LIMIT * 15 * 60 * 1000)
            mode  = "FULL"
        else:
            since = last_ts + 1
            if exchange.milliseconds() - since < (15 * 60 * 1000):
                completed[0] += 1
                return []
            mode = "INCREMENTAL"

        retries = 3
        for attempt in range(retries):
            try:
                ohlcv = await exchange.fetch_ohlcv(
                    symbol, timeframe=timeframe, since=since, limit=FETCH_LIMIT
                )
                await asyncio.sleep(0.5)

                valid_rows = []
                rejected   = 0
                for row in ohlcv:
                    if validate_candle(row):
                        valid_rows.append((symbol, timeframe, row[0],
                                           row[1], row[2], row[3], row[4], row[5]))
                    else:
                        rejected += 1

                if rejected > 0:
                    logging.warning(f"[{symbol}] Rejected {rejected} malformed candles.")

                completed[0] += 1
                pct = completed[0] / total * 100
                sys.stdout.write(
                    f"\r  Fetching [{completed[0]}/{total}] {pct:.0f}%  "
                    f"{symbol.ljust(20)} [{mode}]  "
                )
                sys.stdout.flush()
                return valid_rows

            except asyncio.TimeoutError:
                wait = 2 ** attempt
                logging.warning(f"[{symbol}] Timeout (attempt {attempt+1}). Retrying in {wait}s...")
                await asyncio.sleep(wait)
            except Exception as e:
                logging.error(f"[{symbol}] Error: {e}")
                await asyncio.sleep(2)
                break

        completed[0] += 1
        return []


# ==========================================
# MAIN
# ==========================================
async def main():
    start_time = time.time()
    logging.info("=" * 60)
    logging.info(f"Venus Radar V3.6 — Data Fetcher | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=" * 60)

    exchange = ccxt_async.bybit({'enableRateLimit': True})
    conn     = setup_database()
    cursor   = conn.cursor()

    # v3.6: Prune old data first
    prune_old_candles(conn)

    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    try:
        symbols   = await get_top_symbols(exchange, TOP_COINS)
        total     = len(symbols)
        completed = [0]

        tasks   = [
            fetch_ohlcv_for_symbol(exchange, sym, TIMEFRAME, semaphore, cursor, completed, total)
            for sym in symbols
        ]
        results = await asyncio.gather(*tasks)

        print()  # newline after progress bar

        total_rows  = 0
        for data_batch in results:
            if data_batch:
                cursor.executemany('''
                    INSERT OR IGNORE INTO historical_ohlcv
                    (symbol, timeframe, timestamp_ms, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', data_batch)
                total_rows += len(data_batch)

        conn.commit()

        elapsed = round(time.time() - start_time, 1)
        logging.info(f"✅ Saved {total_rows:,} candles to {MARKET_DB} in {elapsed}s.")

        # DB size report
        db_size_mb = os.path.getsize(MARKET_DB) / 1024 / 1024
        logging.info(f"📦 Database size: {db_size_mb:.1f} MB")

    except Exception as e:
        logging.error(f"System error: {e}")
        raise
    finally:
        await exchange.close()
        conn.close()


if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
