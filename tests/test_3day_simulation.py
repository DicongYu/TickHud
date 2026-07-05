#!/usr/bin/env python3
"""3-day simulation validation: midnight reset, daily PnL, no crashes."""

import asyncio
import datetime
import logging
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.engine.mock_engine import MockEngine
from src.db.local_store import LocalStore

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("sim")


def _seed(store: LocalStore):
    import random
    random.seed(42)
    today = datetime.date.today()
    eq = 10000.0
    store.clear_all_baselines()
    for i in range(45, -1, -1):
        d = today - datetime.timedelta(days=i)
        change = random.uniform(-400, 500)
        eq = max(8000, eq + change)
        store.save_baseline(d.strftime("%Y-%m-%d"), round(eq, 2))
    store.save_baseline(today.strftime("%Y-%m-%d"), 10000.0)
    return today


async def simulate():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()

    store = LocalStore(db_path)
    store.open()
    today = _seed(store)

    engine = MockEngine()
    engine.set_baseline(10000.0, today.strftime("%Y-%m-%d"), 0.0)
    await engine.start()

    passed = 0
    failed = 0

    try:
        for day_num in range(1, 4):
            day_label = f"Day {day_num}"
            ticks = 0
            daily_pnl_start = None
            equity_start = None

            while ticks < 500:
                await asyncio.sleep(0.002)
                snap = engine.snapshot
                ticks += 1

                if ticks == 1:
                    daily_pnl_start = snap.daily_pnl
                    equity_start = snap.equity

                if ticks % 100 == 0:
                    eq = snap.equity
                    dp = snap.daily_pnl
                    logger.info(
                        "  %s tick=%d eq=%.2f daily=%.2f baseline=%.2f open=%.2f",
                        day_label, ticks, eq, dp,
                        engine._baseline_equity or 0,
                        snap.open_pnl,
                    )

            if day_num == 1:
                now = datetime.datetime.now()
                future = now + datetime.timedelta(days=day_num)
                date_str = future.strftime("%Y-%m-%d")
            else:
                date_str = (datetime.date.today() + datetime.timedelta(days=day_num)).strftime("%Y-%m-%d")

            # Simulate midnight baseline save
            final_snap = engine.snapshot
            baseline_val = final_snap.equity
            store.save_baseline(date_str, baseline_val)
            engine.set_baseline(baseline_val, date_str, 0.0)

            await asyncio.sleep(0.15)
            snap_after = engine.snapshot
            logger.info(
                "  %s MIDNIGHT: baseline=%.2f daily_before=%.2f daily_after=%.2f",
                day_label, baseline_val, daily_pnl_start, snap_after.daily_pnl,
            )

            # Daily PnL after midnight should track only the oscillation since baseline reset
            expected_dp = round(snap_after.equity - baseline_val, 2)
            if abs(snap_after.daily_pnl - expected_dp) < 0.02:
                logger.info("  %s OK: daily=%.2f matches eq-baseline=%.2f", day_label, snap_after.daily_pnl, expected_dp)
                passed += 1
            else:
                logger.warning("  %s FAIL: daily=%.2f != expected=%.2f", day_label, snap_after.daily_pnl, expected_dp)
                failed += 1

            # Verify: total equity should never be 0 or negative
            if snap_after.equity <= 0:
                logger.warning("  %s FAIL: equity=%.2f <= 0", day_label, snap_after.equity)
                failed += 1

    finally:
        await engine.stop()
        store.close()
        os.unlink(db_path)

    logger.info("")
    logger.info("=== Simulation complete ===")
    logger.info("Passed: %d / %d", passed, passed + failed)
    return failed == 0


def main():
    ok = asyncio.run(simulate())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
