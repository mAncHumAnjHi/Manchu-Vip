"""Send a Bitcoin price alert to Telegram.

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
    inr_ticker = yf.Ticker("INR=X")

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

    if btc_history.empty:
        raise RuntimeError("Yahoo Finance returned no Bitcoin price data.")
    if inr_history.empty:
        raise RuntimeError("Yahoo Finance returned no USD/INR data.")

    btc_history = btc_history.dropna(subset=["Close"])
    inr_history = inr_history.dropna(subset=["Close"])

    current_btc_usd = as_float(btc_history["Close"].iloc[-1])
    current_usd_inr = as_float(inr_history["Close"].iloc[-1])
    if current_btc_usd <= 0 or current_usd_inr <= 0:
        raise RuntimeError("Yahoo Finance returned an invalid price.")

    latest_timestamp = btc_history.index[-1]
    target_timestamp = latest_timestamp - dt.timedelta(hours=24)
    earlier_rows = btc_history.loc[btc_history.index <= target_timestamp]
    if earlier_rows.empty:
        raise RuntimeError("Not enough Bitcoin history for a 24-hour comparison.")

    previous_btc_usd = as_float(earlier_rows["Close"].iloc[-1])
    change = current_btc_usd - previous_btc_usd
    change_pct = (change / previous_btc_usd * 100) if previous_btc_usd else 0.0
    market_cap, volume = get_optional_btc_stats(btc_ticker)

    return {
        "usd": current_btc_usd,
        "inr": current_btc_usd * current_usd_inr,
        "inr_rate": current_usd_inr,
        "change": change,
        "change_pct": change_pct,
        "market_cap": market_cap,
        "volume": volume,
    }


def create_message(data: dict[str, float]) -> str:
    change = data["change"]
    sign = "+" if change >= 0 else ""
    emoji = "🟢" if change >= 0 else "🔴"
    timestamp = dt.datetime.now().astimezone().strftime("%d-%b-%Y | %I:%M %p %Z")

    lines = [
        "₿ BITCOIN DAILY ALERT ₿",
        f"📅 {timestamp}",
        "",
        f"💰 Price (USD): ${data['usd']:,.2f}",
        f"💸 Price (INR): ₹{data['inr']:,.2f}",
        f"💱 USD/INR Rate: ₹{data['inr_rate']:.2f}",
        "",
        (
            f"{emoji} 24h Change: {sign}${data['change']:,.2f} "
            f"({sign}{data['change_pct']:.2f}%)"
        ),
        "",
    ]

    if data["market_cap"]:
        lines.append(f"📊 Market Cap: {format_large_number(data['market_cap'])}")
    if data["volume"]:
        lines.append(f"🔄 Volume: {format_large_number(data['volume'])}")

    return "\n".join(lines)


def send_telegram_message(message: str, settings: Settings) -> None:
    url = (
        f"https://api.telegram.org/bot"
        f"{settings.telegram_bot_token}/sendMessage"
    )
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": message,
    }

    try:
        response = requests.post(
            url,
            data=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(f"Telegram request failed: {error}") from error

    result = response.json()
    if not result.get("ok"):
        description = result.get("description", "Unknown Telegram error")
        raise RuntimeError(f"Telegram rejected the message: {description}")


def main() -> int:
    try:
        settings = load_settings()
        print("Fetching Bitcoin data...")
        btc_data = get_btc_data()
        message = create_message(btc_data)

        print("\n--- Preview ---")
        print(message)
        print("---------------\n")

        send_telegram_message(message, settings)
        print("✅ Alert sent successfully!")
        return 0
    except Exception as error:
        print(f"❌ Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())