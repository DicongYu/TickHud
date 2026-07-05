from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from queue import Queue
import base64
import hashlib
import hmac
import os
import socket
from datetime import datetime, timezone
from typing import Optional, Any

import aiohttp
import ccxt.async_support as ccxt_async
from ccxt.async_support import Exchange as AsyncExchange

logger = logging.getLogger(__name__)


class OkxRestClient:
    def __init__(self, api_key: str, api_secret: str, api_password: str, timeout: float = 10):
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_password = api_password
        self._timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None:
            kwargs = {}
            proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("http_proxy")
            if proxy:
                kwargs["proxy"] = proxy
            else:
                kwargs["connector"] = aiohttp.TCPConnector(family=socket.AF_INET)
            self._session = aiohttp.ClientSession(**kwargs)

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    def _sign(self, method: str, path: str, body: str = "") -> dict:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        msg = ts + method.upper() + path + body
        sig = hmac.new(self._api_secret.encode(), msg.encode(), hashlib.sha256).digest()
        sig_b64 = base64.b64encode(sig).decode()
        return {
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": sig_b64,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self._api_password,
        }

    async def _get(self, path: str) -> dict:
        await self._ensure_session()
        headers = self._sign("GET", path)
        url = "https://www.okx.com" + path
        async with self._session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=self._timeout)) as resp:
            data = await resp.json()
            if data.get("code") != "0":
                logger.warning("OKX API error %s: %s", data.get("code"), data.get("msg"))
            return data

    async def fetch_balance(self) -> dict:
        return await self._get("/api/v5/account/balance")

    async def fetch_positions(self) -> dict:
        return await self._get("/api/v5/account/positions")


@dataclass
class MarketSnapshot:
    equity: float = 0.0
    equity_pct: float = 0.0
    open_pnl: float = 0.0
    open_pnl_pct: float = 0.0
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    connected: bool = False
    timestamp: float = 0.0
    latency_ms: float = 0.0


class DataEngine:
    def __init__(self, exchange_name: str = "okx"):
        self._exchange_name = exchange_name
        self._exchange: Optional[AsyncExchange] = None
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._queue: Queue = Queue(maxsize=256)
        self._snapshot = MarketSnapshot()

        self._balance_raw: dict = {}
        self._positions_raw: list[dict] = []
        self._lock = asyncio.Lock()

        self._baseline_equity: Optional[float] = None
        self._net_deposit: float = 0.0
        self._baseline_date: Optional[str] = None

        self._prev_equity: float = 0.0
        self._prev_open_pnl: float = 0.0
        self._connected = False
        self._last_update: float = 0.0
        self._latency_ms: float = 0.0

        self._api_key: str = ""
        self._api_secret: str = ""
        self._api_password: str = ""

        self._use_ws = True
        self._poll_interval: float = 1.0
        self._rest_client: Optional[OkxRestClient] = None
        self._on_transfer: Optional[callable] = None

    @property
    def queue(self) -> Queue:
        return self._queue

    @property
    def snapshot(self) -> MarketSnapshot:
        return self._snapshot

    def set_baseline(self, equity: float, date_str: str, net_deposit: float = 0.0):
        self._baseline_equity = equity
        self._baseline_date = date_str
        self._net_deposit = net_deposit

    def has_baseline(self) -> bool:
        return self._baseline_equity is not None

    async def start(self, api_key: str, api_secret: str, api_password: str = ""):
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_password = api_password
        self._running = True
        self._exchange = self._new_exchange()

        self._tasks = [
            asyncio.create_task(self._watch_balance_loop()),
            asyncio.create_task(self._watch_positions_loop()),
            asyncio.create_task(self._connection_monitor()),
        ]
        logger.info("DataEngine started (mode=ws)")

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._exchange:
            await self._exchange.close()
        if self._rest_client:
            await self._rest_client.close()
        logger.info("DataEngine stopped")

    def _new_exchange(self):
        ex_cls = getattr(ccxt_async, self._exchange_name, None)
        if ex_cls is None:
            raise ValueError(f"Unsupported exchange: {self._exchange_name}")
        return ex_cls({
            "apiKey": self._api_key,
            "secret": self._api_secret,
            "password": self._api_password,
            "enableRateLimit": True,
        })

    def _make_rest_client(self) -> OkxRestClient:
        return OkxRestClient(self._api_key, self._api_secret, self._api_password)

    async def _fetch_balance_rest(self) -> dict:
        if self._exchange_name == "okx":
            if self._rest_client is None:
                self._rest_client = self._make_rest_client()
            raw = await self._rest_client.fetch_balance()
            data = raw.get("data", [{}])
            if data:
                return {
                    "info": {"data": data},
                    "USDT": {"total": float(data[0].get("totalEq", 0))},
                }
            return {}
        else:
            return await self._exchange.fetchBalance()

    async def _fetch_positions_rest(self) -> list[dict]:
        if self._exchange_name == "okx":
            if self._rest_client is None:
                self._rest_client = self._make_rest_client()
            raw = await self._rest_client.fetch_positions()
            return raw.get("data", [])
        else:
            pos = await self._exchange.fetchPositions()
            return pos if isinstance(pos, list) else []

    async def _watch_balance_loop(self):
        while self._running:
            try:
                bal = await self._exchange.watchBalance({"type": "total"})
                self._connected = True
                self._last_update = time.time()
                async with self._lock:
                    self._balance_raw = bal
                self._publish()
            except asyncio.CancelledError:
                break
            except Exception as e:
                err_name = type(e).__name__
                if "NotSupported" in err_name:
                    logger.warning("WS not supported for %s, switching to REST polling", self._exchange_name)
                    await self._run_poll_balance()
                    break
                logger.warning("Balance WS error: %s", e)
                self._connected = False
                self._publish_disconnected()
                await asyncio.sleep(2)

    async def _watch_positions_loop(self):
        while self._running:
            try:
                pos = await self._exchange.watchPositions()
                self._connected = True
                self._last_update = time.time()
                async with self._lock:
                    self._positions_raw = pos if isinstance(pos, list) else []
                self._publish()
            except asyncio.CancelledError:
                break
            except Exception as e:
                err_name = type(e).__name__
                if "NotSupported" in err_name:
                    logger.warning("WS not supported for %s, switching to REST polling", self._exchange_name)
                    await self._run_poll_positions()
                    break
                logger.warning("Position WS error: %s", e)
                self._connected = False
                self._publish_disconnected()
                await asyncio.sleep(2)

    async def _run_poll_balance(self):
        retry = 1
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
                t0 = time.monotonic()
                bal = await self._fetch_balance_rest()
                self._latency_ms = round((time.monotonic() - t0) * 1000, 1)
                retry = 1
                self._connected = True
                self._last_update = time.time()
                async with self._lock:
                    self._balance_raw = bal
                self._publish()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Balance REST error (retry=%d): %s", retry, e)
                self._connected = False
                self._publish_disconnected()
                await asyncio.sleep(min(retry, 60))
                retry = min(retry * 2, 60)

    async def _run_poll_positions(self):
        retry = 1
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
                t0 = time.monotonic()
                pos = await self._fetch_positions_rest()
                self._latency_ms = round((time.monotonic() - t0) * 1000, 1)
                retry = 1
                self._connected = True
                self._last_update = time.time()
                async with self._lock:
                    self._positions_raw = pos
                self._publish()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Position REST error (retry=%d): %s", retry, e)
                self._connected = False
                self._publish_disconnected()
                await asyncio.sleep(min(retry, 60))
                retry = min(retry * 2, 60)

    async def _reconnect_backoff(self, retry: int):
        delay = min(retry, 60)
        logger.info("Reconnecting in %ds...", delay)
        await asyncio.sleep(delay)
        try:
            if self._exchange:
                await self._exchange.close()
        except Exception:
            pass
        self._exchange = self._new_exchange()

    async def _connection_monitor(self):
        while self._running:
            await asyncio.sleep(2)
            if self._last_update > 0 and time.time() - self._last_update > 5:
                if self._connected:
                    logger.warning("No data for 5s, marking disconnected")
                self._connected = False

    def _publish_disconnected(self):
        snap = MarketSnapshot(
            equity=0.0,
            equity_pct=0.0,
            open_pnl=0.0,
            open_pnl_pct=0.0,
            daily_pnl=0.0,
            daily_pnl_pct=0.0,
            connected=False,
            timestamp=time.time(),
        )
        self._snapshot = snap

    def _publish(self):
        eq, eq_pct = self._compute_equity()
        op, op_pct = self._compute_open_pnl()
        dp, dp_pct = self._compute_daily_pnl(eq)

        self._detect_transfer(eq, op)

        self._snapshot = MarketSnapshot(
            equity=eq,
            equity_pct=eq_pct,
            open_pnl=op,
            open_pnl_pct=op_pct,
            daily_pnl=dp,
            daily_pnl_pct=dp_pct,
            connected=self._connected,
            timestamp=time.time(),
            latency_ms=self._latency_ms,
        )
        self._prev_equity = eq
        self._prev_open_pnl = op

    def _detect_transfer(self, equity: float, open_pnl: float):
        if self._prev_equity is None or self._prev_equity == 0:
            return
        if self._baseline_equity is None:
            return
        eq_change = equity - self._prev_equity
        pnl_change = open_pnl - self._prev_open_pnl
        net_sans_pnl = eq_change - pnl_change
        threshold = max(2, abs(self._baseline_equity) * 0.005)
        if abs(net_sans_pnl) >= threshold:
            amount = round(net_sans_pnl, 2)
            self._net_deposit += amount
            logger.info("Transfer detected: %+.2f (net_deposit=%+.2f)", net_sans_pnl, self._net_deposit)
            if self._on_transfer:
                self._on_transfer(amount)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _compute_equity(self) -> tuple[float, float]:
        if not self._balance_raw:
            return 0.0, 0.0

        usdt_total = self._safe_float(self._balance_raw.get("USDT", {}).get("total"), 0.0)
        total = usdt_total
        total_usd = 0.0

        info = self._balance_raw.get("info", {})
        data = info.get("data", [{}]) if isinstance(info, dict) else [{}]

        if data and isinstance(data, list) and len(data) > 0:
            total_eq_str = data[0].get("totalEq", "")
            if total_eq_str:
                total_usd = self._safe_float(total_eq_str)

        if total_usd > 0:
            total = total_usd
        else:
            for currency, amounts in self._balance_raw.items():
                if currency in ("info", "timestamp", "datetime", "free", "used", "total"):
                    continue
                if currency == "USDT":
                    continue
                tot = self._safe_float(amounts.get("total"))
                if tot:
                    total += self._approx_usd(currency, tot)

        return round(total, 2), 0.0

    @staticmethod
    def _approx_usd(currency: str, amount: float) -> float:
        if currency == "USDT":
            return amount
        if currency == "USD":
            return amount
        if currency == "BTC":
            return amount * 60000
        if currency == "ETH":
            return amount * 3500
        if currency == "SOL":
            return amount * 150
        if currency == "OKB":
            return amount * 40
        return 0.0

    def _compute_open_pnl(self) -> tuple[float, float]:
        if not self._positions_raw:
            return 0.0, 0.0

        total_pnl = 0.0
        weighted_pct = 0.0
        count = 0

        for pos in self._positions_raw:
            upnl = pos.get("upl") or pos.get("unrealizedPnl") or 0
            total_pnl += self._safe_float(upnl)

            pct_raw = pos.get("uplRatio") or pos.get("percentage")
            if pct_raw is not None:
                pct_f = self._safe_float(pct_raw)
                if pct_f != 0:
                    weighted_pct += pct_f * (100 if self._exchange_name == "okx" else 1)
                    count += 1

        avg_pct = weighted_pct / count if count else 0.0
        return round(total_pnl, 2), round(avg_pct, 2)

    def _compute_daily_pnl(self, current_equity: float) -> tuple[float, float]:
        if self._baseline_equity is None:
            return 0.0, 0.0
        pnl = current_equity - self._baseline_equity - self._net_deposit
        pct = 0.0
        if self._baseline_equity != 0:
            pct = pnl / abs(self._baseline_equity) * 100
        return round(pnl, 2), round(pct, 2)
