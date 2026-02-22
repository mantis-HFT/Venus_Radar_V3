"""
ml_retrain.py — Venus Radar V3.6
Python-based ML Pipeline Launcher (alternative to auto_retrain_loop.bat)

Runs data_fetcher → model backup → train_ppas in sequence.
Logs output to logs/ml_retrain_YYYYMMDD.log.
"""

import subprocess
import logging
import datetime
import os
import shutil
import sys

# Setup Logging
os.makedirs('logs', exist_ok=True)
log_filename = f"logs/ml_retrain_{datetime.datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# Also print to console
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


def run_script(script_path):
    logging.info(f"🚀 Running: {script_path}")
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            check=True
        )
        logging.info(f"✅ Completed {script_path}:\n{result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Failed {script_path}:\n{e.stderr}")
        return False


def backup_old_model():
    src = "ml_enhancements/ppas_global_model.pkl"
    dst = "ml_enhancements/ppas_global_model_backup.pkl"
    if os.path.exists(src):
        shutil.copy2(src, dst)
        logging.info(f"📦 Model backed up → {dst}")
    else:
        logging.info("No existing model to backup (first run).")


def main():
    logging.info("=" * 60)
    logging.info("VENUS RADAR V3.6 — ML RETRAIN PIPELINE START")
    logging.info(f"Timestamp: {datetime.datetime.now().isoformat()}")
    logging.info("=" * 60)

    # Step 1: Fetch data
    if not run_script('ml_enhancements/data_fetcher.py'):
        logging.error("Pipeline aborted at data fetch step.")
        return

    # Step 2: Backup
    backup_old_model()

    # Step 3: Train
    if run_script('ml_enhancements/train_ppas.py'):
        logging.info("🎉 Pipeline completed successfully. New model is live.")
    else:
        logging.error("Pipeline failed at training step. Old model retained.")


if __name__ == "__main__":
    main()
