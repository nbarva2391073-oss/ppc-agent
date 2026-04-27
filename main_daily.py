# ============================================================
# ЩОДЕННИЙ ЗАПУСК — entrypoint для GitHub Actions
# ============================================================

from monitor import run_daily_monitor

if __name__ == "__main__":
    run_daily_monitor()
