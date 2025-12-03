#!/usr/bin/env python3
import time
import subprocess
import sys
from datetime import datetime

def run_experiment():
    """Run the main experiment script"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Starting experiment run...")
    
    try:
        result = subprocess.run(
            ["python3", "main.py"],
            check=True,
            capture_output=False
        )
        print(f"[{timestamp}] Experiment completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[{timestamp}] Experiment failed with error: {e}")
        return False

def main():
    interval_seconds = 3600  # 1 hour
    
    # Run immediately on startup
    run_experiment()
    
    # Then run every hour
    while True:
        time.sleep(interval_seconds)
        run_experiment()

if __name__ == "__main__":
    main()