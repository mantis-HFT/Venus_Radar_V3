"""
Venus Radar V2 - Utilities
Helper scripts for database queries and maintenance
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import argparse

DB_PATH = "pdrs_venus_radar_v2.db"

def view_recent_alerts(hours=24):
    """View recent alerts"""
    conn = sqlite3.connect(DB_PATH)
    query = f"""
        SELECT 
            timestamp,
            symbol,
            alert_level,
            ppas_score,
            deviation,
            rp_score,
            exchange
        FROM alerts_history
        WHERE timestamp > datetime('now', '-{hours} hours')
        ORDER BY timestamp DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print(f"No alerts in the last {hours} hours")
    else:
        print(f"\n{'='*80}")
        print(f"Recent Alerts (Last {hours} hours)")
        print('='*80)
        print(df.to_string(index=False))
        print(f"\nTotal alerts: {len(df)}")
    
    return df

def view_top_alerts(limit=20):
    """View highest PPAS alerts all-time"""
    conn = sqlite3.connect(DB_PATH)
    query = f"""
        SELECT 
            timestamp,
            symbol,
            alert_level,
            ppas_score,
            deviation,
            rp_score,
            exchange
        FROM alerts_history
        ORDER BY ppas_score DESC
        LIMIT {limit}
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print("No alerts found")
    else:
        print(f"\n{'='*80}")
        print(f"Top {limit} Alerts by PPAS Score")
        print('='*80)
        print(df.to_string(index=False))
    
    return df

def view_symbol_history(symbol, days=7):
    """View history for a specific symbol"""
    conn = sqlite3.connect(DB_PATH)
    
    # Get alerts
    query_alerts = f"""
        SELECT 
            timestamp,
            alert_level,
            ppas_score,
            deviation,
            rp_score
        FROM alerts_history
        WHERE symbol = ?
        AND timestamp > datetime('now', '-{days} days')
        ORDER BY timestamp DESC
    """
    df_alerts = pd.read_sql_query(query_alerts, conn, params=(symbol,))
    
    # Get rankings
    query_rankings = f"""
        SELECT 
            scan_timestamp,
            ppas_score,
            deviation,
            rp_score,
            volume_24h
        FROM coin_rankings
        WHERE symbol = ?
        AND scan_timestamp > datetime('now', '-{days} days')
        ORDER BY scan_timestamp DESC
        LIMIT 50
    """
    df_rankings = pd.read_sql_query(query_rankings, conn, params=(symbol,))
    conn.close()
    
    print(f"\n{'='*80}")
    print(f"History for {symbol} (Last {days} days)")
    print('='*80)
    
    if not df_alerts.empty:
        print(f"\nAlerts ({len(df_alerts)}):")
        print(df_alerts.to_string(index=False))
    else:
        print("\nNo alerts for this symbol")
    
    if not df_rankings.empty:
        print(f"\n\nRecent Rankings (Last 50 scans):")
        print(df_rankings.to_string(index=False))
    else:
        print("\nNo ranking data for this symbol")
    
    return df_alerts, df_rankings

def view_statistics():
    """View overall statistics"""
    conn = sqlite3.connect(DB_PATH)
    
    # Total alerts
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM alerts_history")
    total_alerts = cursor.fetchone()[0]
    
    # Alerts by level
    cursor.execute("""
        SELECT alert_level, COUNT(*) 
        FROM alerts_history 
        GROUP BY alert_level
    """)
    alerts_by_level = cursor.fetchall()
    
    # Most alerted symbols
    cursor.execute("""
        SELECT symbol, COUNT(*) as count
        FROM alerts_history
        GROUP BY symbol
        ORDER BY count DESC
        LIMIT 10
    """)
    top_symbols = cursor.fetchall()
    
    # Recent scan count
    cursor.execute("""
        SELECT COUNT(DISTINCT scan_timestamp)
        FROM coin_rankings
        WHERE scan_timestamp > datetime('now', '-24 hours')
    """)
    scans_24h = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n{'='*80}")
    print("Venus Radar Statistics")
    print('='*80)
    
    print(f"\nTotal Alerts: {total_alerts}")
    
    print("\nAlerts by Level:")
    for level, count in alerts_by_level:
        print(f"  {level}: {count}")
    
    print(f"\nScans in Last 24h: {scans_24h}")
    
    print("\nMost Alerted Symbols:")
    for i, (symbol, count) in enumerate(top_symbols, 1):
        print(f"  {i}. {symbol}: {count} alerts")

def export_to_csv(table_name, output_file=None):
    """Export a table to CSV"""
    if output_file is None:
        output_file = f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    conn.close()
    
    df.to_csv(output_file, index=False)
    print(f"Exported {len(df)} rows to {output_file}")

def clean_old_data(days=30):
    """Clean data older than specified days"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Clean old alerts
    cursor.execute(f"""
        DELETE FROM alerts_history
        WHERE timestamp < datetime('now', '-{days} days')
    """)
    alerts_deleted = cursor.rowcount
    
    # Clean old rankings
    cursor.execute(f"""
        DELETE FROM coin_rankings
        WHERE scan_timestamp < datetime('now', '-{days} days')
    """)
    rankings_deleted = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"Cleaned {alerts_deleted} old alerts")
    print(f"Cleaned {rankings_deleted} old rankings")
    print(f"Data older than {days} days has been removed")

def main():
    parser = argparse.ArgumentParser(description='Venus Radar V2 Utilities')
    parser.add_argument('command', choices=[
        'recent-alerts', 'top-alerts', 'symbol-history', 
        'stats', 'export', 'clean'
    ], help='Command to run')
    parser.add_argument('--hours', type=int, default=24, help='Hours for recent-alerts')
    parser.add_argument('--days', type=int, default=7, help='Days for symbol-history or clean')
    parser.add_argument('--limit', type=int, default=20, help='Limit for top-alerts')
    parser.add_argument('--symbol', type=str, help='Symbol for symbol-history')
    parser.add_argument('--table', type=str, choices=['alerts_history', 'coin_rankings'], 
                       help='Table for export')
    parser.add_argument('--output', type=str, help='Output file for export')
    
    args = parser.parse_args()
    
    if args.command == 'recent-alerts':
        view_recent_alerts(args.hours)
    
    elif args.command == 'top-alerts':
        view_top_alerts(args.limit)
    
    elif args.command == 'symbol-history':
        if not args.symbol:
            print("Error: --symbol required for symbol-history")
            return
        view_symbol_history(args.symbol, args.days)
    
    elif args.command == 'stats':
        view_statistics()
    
    elif args.command == 'export':
        if not args.table:
            print("Error: --table required for export")
            return
        export_to_csv(args.table, args.output)
    
    elif args.command == 'clean':
        response = input(f"This will delete data older than {args.days} days. Continue? (yes/no): ")
        if response.lower() == 'yes':
            clean_old_data(args.days)
        else:
            print("Cancelled")

if __name__ == "__main__":
    # If run without arguments, show interactive menu
    import sys
    if len(sys.argv) == 1:
        print("\n" + "="*60)
        print("Venus Radar V2 - Database Utilities")
        print("="*60)
        print("\nAvailable commands:")
        print("  1. View recent alerts")
        print("  2. View top alerts")
        print("  3. View symbol history")
        print("  4. View statistics")
        print("  5. Export to CSV")
        print("  6. Clean old data")
        print("  0. Exit")
        print("\nOr use command line:")
        print("  python utils.py stats")
        print("  python utils.py recent-alerts --hours 48")
        print("  python utils.py symbol-history --symbol BTC/USDT --days 7")
        print("  python utils.py export --table alerts_history")
        print()
        
        choice = input("Enter choice (0-6): ")
        
        if choice == '1':
            hours = input("Hours to view (default 24): ") or "24"
            view_recent_alerts(int(hours))
        elif choice == '2':
            limit = input("Number of alerts (default 20): ") or "20"
            view_top_alerts(int(limit))
        elif choice == '3':
            symbol = input("Symbol (e.g., BTC/USDT): ")
            days = input("Days to view (default 7): ") or "7"
            view_symbol_history(symbol, int(days))
        elif choice == '4':
            view_statistics()
        elif choice == '5':
            print("Tables: alerts_history, coin_rankings")
            table = input("Table to export: ")
            export_to_csv(table)
        elif choice == '6':
            days = input("Delete data older than (days): ")
            response = input(f"This will delete data older than {days} days. Continue? (yes/no): ")
            if response.lower() == 'yes':
                clean_old_data(int(days))
        elif choice == '0':
            print("Goodbye!")
        else:
            print("Invalid choice")
    else:
        main()
