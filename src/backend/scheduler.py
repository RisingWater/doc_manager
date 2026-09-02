from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from . import scanner
from .config import SCAN_INTERVAL_MINUTES

_scheduler: BackgroundScheduler | None = None


def _scheduled_scan() -> None:
    try:
        scanner.start_scan("auto")
    except Exception as exc:
        print(f"[scheduler] 自动扫描失败: {exc}")


def start_scheduler() -> None:
    global _scheduler
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _scheduled_scan,
        "interval",
        minutes=SCAN_INTERVAL_MINUTES,
        id="scan_documents",
        replace_existing=True,
        next_run_time=datetime.now() + timedelta(seconds=10),
    )
    _scheduler.start()
    print(f"[scheduler] 自动扫描已启动，每 {SCAN_INTERVAL_MINUTES} 分钟执行一次")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
