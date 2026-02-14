"""
Test script for Venus Radar V2
Run this to verify your installation and API connectivity
"""

import sys
import importlib

def test_dependencies():
    """Test if all required packages are installed"""
    print("Testing dependencies...")
    required = ['ccxt', 'pandas', 'numpy', 'requests', 'sqlite3']
    
    missing = []
    for package in required:
        try:
            importlib.import_module(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package} - MISSING")
            missing.append(package)
    
    if missing:
        print(f"\nError: Missing packages: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt")
        return False
    
    print("All dependencies installed!\n")
    return True

def test_config():
    """Test if config file exists and is valid"""
    print("Testing config file...")
    try:
        import config as cfg
        print("  ✓ config.py found")
        
        # Test key settings
        print(f"  ✓ Exchange: {cfg.EXCHANGE}")
        print(f"  ✓ Scan interval: {cfg.SCAN_INTERVAL_MINUTES} minutes")
        print(f"  ✓ Telegram enabled: {cfg.TELEGRAM_ENABLED}")
        
        if cfg.TELEGRAM_ENABLED:
            if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
                print("  ⚠ Telegram enabled but credentials missing!")
        
        print("Config file OK!\n")
        return True
    except ImportError:
        print("  ✗ config.py not found")
        print("  Make sure config.py is in the same directory\n")
        return False
    except Exception as e:
        print(f"  ✗ Error reading config: {e}\n")
        return False

def test_exchange_connection():
    """Test connection to exchanges"""
    print("Testing exchange connections...")
    
    try:
        import ccxt
        
        # Test Bybit
        try:
            bybit = ccxt.bybit({'enableRateLimit': True})
            ticker = bybit.fetch_ticker('BTC/USDT:USDT')
            print(f"  ✓ Bybit connected - BTC price: ${ticker['last']:,.2f}")
        except Exception as e:
            print(f"  ✗ Bybit connection failed: {e}")
        
        # Test Binance
        try:
            binance = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
            ticker = binance.fetch_ticker('BTC/USDT')
            print(f"  ✓ Binance connected - BTC price: ${ticker['last']:,.2f}")
        except Exception as e:
            print(f"  ✗ Binance connection failed: {e}")
        
        print("Exchange connection test complete!\n")
        return True
        
    except Exception as e:
        print(f"  ✗ Error: {e}\n")
        return False

def test_database():
    """Test database creation"""
    print("Testing database...")
    try:
        import sqlite3
        import os
        
        # Try to create a test database
        test_db = "test_venus.db"
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
        conn.commit()
        conn.close()
        
        if os.path.exists(test_db):
            os.remove(test_db)
            print("  ✓ Database functionality working")
            print("Database test OK!\n")
            return True
        
    except Exception as e:
        print(f"  ✗ Database error: {e}\n")
        return False

def test_single_coin():
    """Test processing a single coin"""
    print("Testing coin processing (this may take 10-15 seconds)...")
    
    try:
        import config as cfg
        from venus_radar_v2_config import VenusRadar
        
        radar = VenusRadar()
        
        # Try processing Bitcoin
        print("  Fetching BTC/USDT data...")
        result = radar.process_single_coin('BTC/USDT:USDT' if cfg.EXCHANGE == 'bybit' else 'BTC/USDT')
        
        if result:
            print(f"  ✓ Successfully processed BTC/USDT")
            print(f"    PPAS Score: {result['ppas']:.2f}")
            print(f"    Deviation: {result['deviation']:.2f}%")
            print(f"    RP Score: {result['rp']:.2f}")
            print("Coin processing test OK!\n")
            return True
        else:
            print("  ✗ Failed to process coin\n")
            return False
            
    except Exception as e:
        print(f"  ✗ Error: {e}\n")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("Venus Radar V2 - Installation Test")
    print("=" * 60)
    print()
    
    results = {
        'Dependencies': test_dependencies(),
        'Config File': test_config(),
        'Exchange Connection': test_exchange_connection(),
        'Database': test_database(),
        'Coin Processing': test_single_coin()
    }
    
    print("=" * 60)
    print("Test Summary:")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:.<30} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n🎉 All tests passed! Venus Radar is ready to run.")
        print("\nTo start the scanner:")
        print("  python venus_radar_v2_config.py")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        print("\nCommon fixes:")
        print("  - Install dependencies: pip install -r requirements.txt")
        print("  - Check your internet connection")
        print("  - Make sure config.py is in the same directory")
    
    print()

if __name__ == "__main__":
    main()
