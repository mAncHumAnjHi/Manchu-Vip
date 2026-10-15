"""Send a Bitcoin price alert to Telegram."""
Setup:
    1. Copy .env.example to .env.
    2. Add your Telegram bot token and chat ID to .env.
    3. Install dependencies: pip install -r requirements.txt
    4. Run: python btc_daily_alert.py
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from dataclasses import dataclass
from typing import Any

import requests
import yfinance as yf
from dotenv import load_dotenv


REQUEST_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str


def load_settings() -> Settings:
    """Load and validate configuration without exposing secret values."""
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    missing = []
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Missing required environment variable(s): {names}. "
            "Copy .env.example to .env and fill in the values."
        )

    return Settings(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
    )


def as_float(value: Any, default: float = 0.0) -> float:
    """Convert yfinance values to floats while handling missing data."""
    try:
        result = float(value)
        return result if result == result else default  # NaN-safe
    except (TypeError, ValueError):
        return default


def format_large_number(value: float) -> str:
    if value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f} Trillion"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f} Billion"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f} Million"
    return f"${value:,.2f}"


def get_optional_btc_stats(ticker: yf.Ticker) -> tuple[float, float]:
    """Return market cap and volume when Yahoo provides them.

    These values are supplementary. If Yahoo changes or omits the info
    response, the price alert still works.
    """
    try:
        info = ticker.info
    except Exception as error:
        print(f"Warning: optional market stats unavailable: {error}")
        return 0.0, 0.0

    market_cap = as_float(info.get("marketCap"))
    volume = as_float(info.get("regularMarketVolume", info.get("volume24Hr")))
    return market_cap, volume


def get_btc_data() -> dict[str, float]:
    """Fetch the current BTC price, INR conversion, and 24-hour movement."""
    btc_ticker = yf.Ticker("BTC-USD")
    inr_ticker = yf.Ticker("USDINR=X")

    # Hourly history gives a real 24-hour comparison for a continuously
    # traded asset, unlike comparing against the previous daily candle.
    btc_history = btc_ticker.history(
        period="3d",
        interval="1h",
        auto_adjust=False,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    inr_history = inr_ticker.history(
        period="1d",
        interval="1h",
        auto_adjust=False,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if inr_history.empty:
    print("Warning: Yahoo Finance se USD/INR data nahi mila. Using fallback rate.")
    current_usd_inr = 83.5  # Fallback rate
else:
    current_usd_inr = as_float(inr_history["Close"].iloc[-1])

    btc_history = btc_history.dropna(subset=["Close"])
    if inr_history.empty:
        print("Warning: Yahoo Finance se USD/INR data nahi mila. Using fallback rate.")
        current_usd_inr = 83.5
    else:
        current_usd_inr = as_float(inr_history["Close"].iloc[-1])

    btc_history = btc_history.dropna(subset=["Close"])

    current_btc_usd = as_float(btc_history["Close"].iloc[-1])

    if current_btc_usd <= 0 or current_usd_inr <= 0: