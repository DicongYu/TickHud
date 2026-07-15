from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from queue import Queue
from typing import Optional

from src.engine.data_engine import MarketSnapshot

logger = logging.getLogger(__name__)


class MockEngine:
    def __init__(self):
        self._queue: Queue = Queue(maxsize=256)
        self._snapshot = MarketSnapshot()
        self._running = False
        self._task: Optional[asyncio.Task] = None

        self._baseline_equity: Optional[float] = None
        self._net_deposit: float = 0.0
        self._baseline_date: Optional[str] = None

        self._midnight_realized_pnl: float = 0.0
        self._realized_pnl: float = 0.0
        self._open_pnl: float = 10.0

        self._t = 0.0

    @property
    def queue(self) -> Queue:
        return self._queue

    @property
    def snapshot(self) -> MarketSnapshot:
        return self._snapshot

    def set_baseline(self, equity: float, date_str: str, net_deposit: float = 0.0, midnight_realized_pnl: float | None = None):
        self._baseline_equity = equity
        self._baseline_date = date_str
        self._net_deposit = net_deposit
        self._midnight_realized_pnl = self._realized_pnl if midnight_realized_pnl is None else midnight_realized_pnl

    def has_baseline(self) -> bool:
        return self._baseline_equity is not None

    def close_half(self):
        half = self._open_pnl / 2
        self._realized_pnl += half
        self._open_pnl = half

    def close_all(self):
        self._realized_pnl += self._open_pnl
        self._open_pnl = 0.0

    def reset(self):
        self._open_pnl = 10.0
        self._realized_pnl = 0.0

    async def start(self, api_key: str = "", api_secret: str = "", api_password: str = ""):
        self._running = True
        self._task = asyncio.create_task(self._simulate_loop())
        logger.info("MockEngine started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MockEngine stopped")

    async def _simulate_loop(self):
        eq = self._baseline_equity or 10000.0

        while self._running:
            self._t += 0.01
            b = self._baseline_equity or eq

            op = self._open_pnl

            dp = self._realized_pnl - self._midnight_realized_pnl
            eq = b + op + self._realized_pnl  # equity = baseline + open + realized

            eq_pct = 0
            if self._prev_eq is not None and self._prev_eq != 0:
                eq_pct = (eq - self._prev_eq) / abs(self._prev_eq) * 100
            else:
                eq_pct = 0.05 * math.cos(self._t * 0.08)

            op_pct = (op / b) * 100 if b else 0
            dp_pct = (dp / b) * 100 if b else 0

            self._prev_eq = eq

            self._log_kpi_counter = getattr(self, "_log_kpi_counter", 0) + 1
            if self._log_kpi_counter >= 300:
                self._log_kpi_counter = 0
                logger.info("KPI: equity=%.2f open_pnl=%.2f daily_pnl=%.2f realized_pnl=%.2f", eq, op, dp, self._realized_pnl)

            self._snapshot = MarketSnapshot(
                equity=round(eq, 2),
                equity_pct=round(eq_pct, 2),
                open_pnl=round(op, 2),
                open_pnl_pct=round(op_pct, 2),
                daily_pnl=round(dp, 2),
                daily_pnl_pct=round(dp_pct, 2),
                realized_pnl=round(self._realized_pnl, 2),
                connected=True,
                timestamp=time.time(),
            )

            await asyncio.sleep(0.1)

    _prev_eq: float = 0.0
    _prev_open_pnl: float = 0.0
