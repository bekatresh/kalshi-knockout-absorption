"""
Thin client for Kalshi's public (unauthenticated) market-data endpoints.

Market data reads (markets, events, candlesticks, trades) do NOT require
an API key. If you hit rate limits, add time.sleep between calls or plug
in your authenticated session from your market-making bot.

VERIFIED LIVE 2026-07-06 against trade-api/v2: all price fields (on both
/markets and candlesticks) are now `<field>_dollars` STRING values (e.g.
"0.0140"), not the older cents-integer convention (`yes_bid`, `last_price`)
-- reading the old field names doesn't 404, it silently returns None. Use
the `dollars()` helper below everywhere a price is read. If Kalshi changes
shape again, check https://trading-api.readme.io/reference.
"""

from __future__ import annotations

import time
from typing import Iterator, Optional

import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"


def dollars(obj: dict, field: str) -> Optional[float]:
    """Read a `<field>_dollars` string field (present on markets and
    candlesticks) as a float, or None if absent/blank."""
    val = obj.get(f"{field}_dollars")
    if val in (None, ""):
        return None
    return float(val)


class KalshiPublic:
    def __init__(self, base: str = BASE, sleep_s: float = 0.15):
        self.base = base
        self.sleep_s = sleep_s
        self.sess = requests.Session()
        self.sess.headers.update({"Accept": "application/json"})

    def _get(self, path: str, **params) -> dict:
        backoff = 1.0
        for _ in range(6):
            r = self.sess.get(f"{self.base}{path}", params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(backoff)
                backoff *= 2
                continue
            r.raise_for_status()
            time.sleep(self.sleep_s)
            return r.json()
        r.raise_for_status()
        return r.json()

    # ---------- discovery ----------

    def iter_events(self, series_ticker: str, status: Optional[str] = None) -> Iterator[dict]:
        """Yield all events for a series (e.g. the World Cup match series)."""
        cursor = None
        while True:
            params = {"series_ticker": series_ticker, "limit": 200}
            if status:
                params["status"] = status
            if cursor:
                params["cursor"] = cursor
            data = self._get("/events", **params)
            for ev in data.get("events", []):
                yield ev
            cursor = data.get("cursor")
            if not cursor:
                break

    def iter_markets(self, series_ticker: Optional[str] = None,
                     event_ticker: Optional[str] = None,
                     status: Optional[str] = None) -> Iterator[dict]:
        cursor = None
        while True:
            params = {"limit": 200}
            if series_ticker:
                params["series_ticker"] = series_ticker
            if event_ticker:
                params["event_ticker"] = event_ticker
            if status:
                params["status"] = status
            if cursor:
                params["cursor"] = cursor
            data = self._get("/markets", **params)
            for m in data.get("markets", []):
                yield m
            cursor = data.get("cursor")
            if not cursor:
                break

    def get_market(self, ticker: str) -> dict:
        return self._get(f"/markets/{ticker}")["market"]

    # ---------- prices ----------

    def candlesticks(self, series_ticker: str, market_ticker: str,
                     start_ts: int, end_ts: int, period_interval: int = 60) -> list[dict]:
        """
        period_interval in minutes: 1, 60, or 1440.
        Returns list of candles with yes bid/ask/price OHLC as `*_dollars`
        string fields (probability units, e.g. "0.0140" = 1.4%) plus
        `volume_fp`. Use kalshi_client.dollars() to parse.
        """
        data = self._get(
            f"/series/{series_ticker}/markets/{market_ticker}/candlesticks",
            start_ts=start_ts, end_ts=end_ts, period_interval=period_interval,
        )
        return data.get("candlesticks", [])
