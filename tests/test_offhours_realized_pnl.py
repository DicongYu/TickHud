#!/usr/bin/env python3
"""Test: off-hours (app not running) realized PnL is correctly restored on startup."""

import asyncio
import datetime
import logging
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.local_store import LocalStore

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("test")


def _seed_midnight_baseline(store: LocalStore):
    """Simulate: midnight saved baseline with realized_pnl = -2.19."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    store.save_baseline(today, 36.77, realized_pnl=-2.19)
    return today


async def test_offhours_realized_pnl():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()

    try:
        store = LocalStore(db_path)
        store.open()
        today = _seed_midnight_baseline(store)
        logger.info("Midnight baseline saved: %s  realized_pnl=-2.19", today)

        # Simulate: app starts later in the day, after positions were closed
        # The current totalPnl (simulated) = -2.19 (midnight) + 50.00 (off-hours profit) = 47.81
        simulated_current_realized_pnl = 47.81

        # Load baseline from DB (as main.py does)
        latest = store.get_latest_baseline()
        assert latest is not None, "No baseline in DB"
        assert latest["date"] == today

        midnight_realized = latest.get("realized_pnl")
        logger.info("Restored midnight_realized from DB: %s", midnight_realized)

        # Compute daily PnL as engine does
        daily_pnl = round(simulated_current_realized_pnl - midnight_realized, 2)
        logger.info("Current realized_pnl (simulated): %.2f", simulated_current_realized_pnl)
        logger.info("Daily PnL: %.2f", daily_pnl)

        # Verify
        assert midnight_realized == -2.19, f"Unexpected midnight_realized: {midnight_realized}"
        assert daily_pnl == 50.00, f"Unexpected daily_pnl: {daily_pnl}"

        logger.info("=== PASS: off-hours profit $50 correctly reflected in daily PnL ===")

    finally:
        store.close()
        os.unlink(db_path)


def main():
    asyncio.run(test_offhours_realized_pnl())
    sys.exit(0)


if __name__ == "__main__":
    main()
