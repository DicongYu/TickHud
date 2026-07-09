#!/usr/bin/env python3
"""
TickHUD — Linux 原生交易悬浮窗 & 本地账本
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import signal
import sys

import qasync
from PyQt6.QtWidgets import QApplication

from src.config.settings import load_config, get_db_path
from src.db.local_store import LocalStore
from src.engine.data_engine import DataEngine
from src.ui.hud_window import HudWindow


class SensitiveFormatter(logging.Formatter):
    _SENSITIVE = re.compile(
        r"(api[_-]?key|api[_-]?secret|api[_-]?password|passphrase|secret)\s*[=:]\s*['\"]?\S+",
        re.IGNORECASE,
    )

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return self._SENSITIVE.sub(r"\1=***", msg)


_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=_FMT)
for h in logging.getLogger().handlers:
    h.setFormatter(SensitiveFormatter(_FMT))
logging.getLogger("ccxt").setLevel(logging.WARNING)
logger = logging.getLogger("main")


def _seed_test_data(store: LocalStore):
    import random
    random.seed(42)
    today = datetime.date.today()
    eq = 10000.0
    store.clear_all_baselines()
    for i in range(45, -1, -1):
        d = today - datetime.timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        change = random.uniform(-400, 500)
        eq = max(8000, eq + change)
        store.save_baseline(date_str, round(eq, 2))
    store.save_baseline(today.strftime("%Y-%m-%d"), 10000.0)
    logger.info("Seeded 45 days of test baseline data")


async def main_async(app: QApplication, use_mock: bool = False):
    cfg = load_config()
    db_path = get_db_path()
    if use_mock:
        db_path = db_path.parent / "ledger_test.db"

    store = LocalStore(db_path)
    store.open()

    if use_mock:
        from src.engine.mock_engine import MockEngine
        _seed_test_data(store)
        engine = MockEngine()
        engine.set_baseline(10000.0, datetime.datetime.now().strftime("%Y-%m-%d"), 0.0)
        logger.info("Using MockEngine with baseline $10,000")
    else:
        engine = DataEngine(exchange_name=cfg.get("exchange", "okx"))
        engine._on_transfer = lambda amt: store.add_transfer(amt, "auto-detect")

    engine_task = asyncio.create_task(
        engine.start(
            api_key=cfg.get("api_key", ""),
            api_secret=cfg.get("api_secret", ""),
            api_password=cfg.get("api_password", ""),
        )
    )

    if not use_mock:
        for _ in range(50):
            await asyncio.sleep(0.2)
            if engine.snapshot.equity != 0:
                break
        current_eq = engine.snapshot.equity
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        latest = store.get_latest_baseline()
        if latest and current_eq > 0 and latest["date"] == today:
            bl_eq = latest["equity_usdt"]
            ratio = abs(bl_eq - current_eq) / max(bl_eq, 1)
            if ratio < 0.2:
                engine.set_baseline(bl_eq, today, 0.0)
                logger.info("Restored baseline %s: %.2f", today, bl_eq)
            else:
                logger.warning("Baseline %.2f differs from equity %.2f (%.0f%%), overwriting", bl_eq, current_eq, ratio * 100)
                realized = engine._compute_realized_pnl()
                store.save_baseline(today, current_eq, realized_pnl=realized)
                engine.set_baseline(current_eq, today, 0.0)
                logger.info("Auto-set baseline to current equity: %.2f", current_eq)
        elif current_eq > 0:
            realized = engine._compute_realized_pnl()
            store.save_baseline(today, current_eq, realized_pnl=realized)
            engine.set_baseline(current_eq, today, 0.0)
            logger.info("First launch: baseline set to current equity: %.2f", current_eq)

    hud = HudWindow(engine, store)
    hud.show()

    if not use_mock:
        async def midnight_baseline_loop():
            while True:
                now = datetime.datetime.now()
                next_midnight = (now + datetime.timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                wait_sec = (next_midnight - now).total_seconds()
                await asyncio.sleep(wait_sec)

                snap = engine.snapshot
                date_str = next_midnight.strftime("%Y-%m-%d")
                realized = engine._compute_realized_pnl()
                store.save_baseline(date_str, snap.equity, realized_pnl=realized)
                engine.set_baseline(snap.equity, date_str, 0.0)
                store.save_snapshot(snap.equity, snap.open_pnl, snap.daily_pnl)
                logger.info("Midnight baseline saved: %s eq=%.2f realized=%.2f", date_str, snap.equity, realized)

        baseline_task = asyncio.create_task(midnight_baseline_loop())
    else:
        baseline_task = None

    def cleanup():
        logger.info("Shutting down...")
        snap = engine.snapshot
        store.save_snapshot(snap.equity, snap.open_pnl, snap.daily_pnl)
        store.close()

    app.aboutToQuit.connect(cleanup)

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        if baseline_task:
            baseline_task.cancel()
        await engine.stop()
        store.close()


def main():
    use_mock = "--test" in sys.argv
    if "--test" in sys.argv:
        sys.argv.remove("--test")

    app = QApplication(sys.argv)
    app.setApplicationName("tickhud")

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    loop.add_signal_handler(signal.SIGINT, loop.stop)

    try:
        loop.run_until_complete(main_async(app, use_mock=use_mock))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
