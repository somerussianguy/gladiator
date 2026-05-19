"""Data source fetchers.

Each fetcher is a function that takes a config dict and returns a float price.
Fetchers are registered by 'type' string, matching the 'data_source.type'
field on nodes in nodes.json.

To add a new data source:
  1. Write a function that takes (config: dict) and returns float.
  2. Register it via @register('your_type_name').
  3. Reference it from nodes.json as {"type": "your_type_name", "config": {...}}.
"""
from __future__ import annotations

from typing import Any, Callable

FetcherFn = Callable[[dict[str, Any]], float]

_REGISTRY: dict[str, FetcherFn] = {}


def register(type_name: str) -> Callable[[FetcherFn], FetcherFn]:
    """Decorator to register a fetcher under a type name."""
    def deco(fn: FetcherFn) -> FetcherFn:
        _REGISTRY[type_name] = fn
        return fn
    return deco


def fetch(data_source: dict[str, Any]) -> float:
    """Dispatch to the right fetcher based on data_source['type']."""
    type_name = data_source.get("type")
    if not type_name:
        raise ValueError("data_source is missing 'type'")
    fetcher = _REGISTRY.get(type_name)
    if fetcher is None:
        raise ValueError(
            f"No fetcher registered for type '{type_name}'. "
            f"Registered: {sorted(_REGISTRY)}"
        )
    return fetcher(data_source.get("config", {}))


# ---- built-in fetchers ----------------------------------------------------

@register("yfinance")
def fetch_yfinance(config: dict[str, Any]) -> float:
    """Fetch latest price for a Yahoo Finance ticker.

    Config: {"ticker": "CL=F"}   # CL=F = WTI crude futures, BZ=F = Brent
    Returns the most recent close from a 1-minute interval over the last day,
    or falls back to .info regular market price.
    """
    import yfinance as yf

    ticker_sym = config.get("ticker")
    if not ticker_sym:
        raise ValueError("yfinance config requires 'ticker'")

    t = yf.Ticker(ticker_sym)

    # Try 1-minute bars first (most recent ~15 min delayed during market hours).
    hist = t.history(period="1d", interval="1m")
    if not hist.empty:
        return float(hist["Close"].iloc[-1])

    # Fall back to .fast_info / .info if intraday is empty (off-hours, etc.).
    try:
        fi = t.fast_info
        price = getattr(fi, "last_price", None)
        if price is not None:
            return float(price)
    except Exception:
        pass

    # Final fallback: daily history.
    daily = t.history(period="5d", interval="1d")
    if not daily.empty:
        return float(daily["Close"].iloc[-1])

    raise RuntimeError(f"No price data returned for ticker '{ticker_sym}'")


@register("manual")
def fetch_manual(config: dict[str, Any]) -> float:
    """Returns a fixed value from config. Useful for placeholder nodes."""
    value = config.get("value")
    if value is None:
        raise ValueError("manual fetcher requires 'value' in config")
    return float(value)


@register("yfinance_activity")
def fetch_yfinance_activity(config: dict[str, Any]) -> float:
    """Activity multiplier for a Yahoo Finance ticker.

    Returns (today's price * today's volume) / (30-day average of price * volume).
    A value of 1.0 means activity matches the 30-day norm; 1.5 means 50% above;
    0.7 means quiet. Captures both price level and trading intensity in one number.

    Config: {"ticker": "CL=F", "lookback_days": 30}   # lookback defaults to 30
    """
    import yfinance as yf

    ticker_sym = config.get("ticker")
    lookback = int(config.get("lookback_days", 30))
    if not ticker_sym:
        raise ValueError("yfinance_activity config requires 'ticker'")
    if lookback < 5:
        raise ValueError("yfinance_activity lookback_days must be >= 5")

    t = yf.Ticker(ticker_sym)
    # Pull enough daily bars to cover the lookback plus today.
    hist = t.history(period=f"{lookback + 5}d", interval="1d")
    if hist.empty or len(hist) < 2:
        raise RuntimeError(
            f"Not enough daily history for '{ticker_sym}' to compute activity"
        )

    # Use price * volume per bar (notional traded value).
    pv = hist["Close"] * hist["Volume"]
    today_pv = float(pv.iloc[-1])
    baseline = float(pv.iloc[-(lookback + 1):-1].mean())  # last `lookback` bars before today
    if baseline <= 0:
        raise RuntimeError(
            f"Baseline activity for '{ticker_sym}' is zero — can't compute ratio"
        )
    return today_pv / baseline
