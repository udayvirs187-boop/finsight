
import pandas as pd
import yfinance as yf


def calculate_rsi(prices, period=14):
    """Calculate RSI using Wilder's smoothing."""
    prices = pd.Series(prices, dtype="float64").dropna()

    if len(prices) < period + 1:
        return None

    changes = prices.diff().dropna()
    gains = changes.clip(lower=0)
    losses = -changes.clip(upper=0)

    average_gain = gains.iloc[:period].mean()
    average_loss = losses.iloc[:period].mean()

    for gain, loss in zip(gains.iloc[period:], losses.iloc[period:]):
        average_gain = (
            average_gain * (period - 1) + gain
        ) / period
        average_loss = (
            average_loss * (period - 1) + loss
        ) / period

    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0

    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def calculate_macd(prices):
    """Calculate MACD (12, 26, 9)."""
    prices = pd.Series(prices, dtype="float64").dropna()

    if len(prices) < 35:
        return None, None, None

    ema_12 = prices.ewm(span=12, adjust=False).mean()
    ema_26 = prices.ewm(span=26, adjust=False).mean()

    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    return (
        float(macd_line.iloc[-1]),
        float(signal_line.iloc[-1]),
        float(histogram.iloc[-1]),
    )


def calculate_relative_volatility(prices):
    """Recent 20-day volatility divided by the preceding 60-day volatility."""
    prices = pd.Series(prices, dtype="float64").dropna()
    returns = prices.pct_change().dropna()

    if len(returns) < 80:
        return None

    recent = returns.iloc[-20:].std(ddof=1)
    baseline = returns.iloc[-80:-20].std(ddof=1)

    if pd.isna(baseline) or baseline == 0:
        return None

    return float(recent / baseline)


def calculate_relative_volume(volume):
    """Latest daily volume divided by the previous 20-day average."""
    volume = pd.Series(volume, dtype="float64").dropna()

    if len(volume) < 21:
        return None

    average_volume = volume.iloc[-21:-1].mean()

    if pd.isna(average_volume) or average_volume == 0:
        return None

    return float(volume.iloc[-1] / average_volume)


def get_stock_data(symbol):
    """Fetch Yahoo Finance data and calculate indicators locally."""
    symbol = symbol.strip().upper()
    ticker = yf.Ticker(symbol)

    # Five years of daily data gives the EMAs a longer warm-up period.
    daily = ticker.history(
        period="5y",
        interval="1d",
        auto_adjust=False
    )

    if daily.empty or "Close" not in daily.columns:
        raise ValueError(
            f"No daily price data found for {symbol}. "
            "Check the ticker symbol or try again later."
        )

    daily = daily.dropna(subset=["Close"])

    daily_close = daily["Close"]
    daily_rsi = calculate_rsi(daily_close)

    macd, macd_signal, macd_histogram = calculate_macd(daily_close)

    relative_volatility = calculate_relative_volatility(daily_close)
    relative_volume = calculate_relative_volume(daily["Volume"])

    # Fetch hourly data for a more recent price and hourly RSI.
    hourly = pd.DataFrame()

    try:
        hourly = ticker.history(
            period="60d",
            interval="1h",
            auto_adjust=False
        )

        if not hourly.empty:
            hourly = hourly.dropna(subset=["Close"])
    except Exception:
        hourly = pd.DataFrame()

    if not hourly.empty:
        latest_price = float(hourly["Close"].iloc[-1])
        previous_price = (
            float(hourly["Close"].iloc[-2])
            if len(hourly) >= 2
            else float(daily_close.iloc[-1])
        )
        hourly_rsi = calculate_rsi(hourly["Close"])
        last_updated = str(hourly.index[-1])
    else:
        latest_price = float(daily_close.iloc[-1])
        previous_price = (
            float(daily_close.iloc[-2])
            if len(daily_close) >= 2
            else latest_price
        )
        hourly_rsi = None
        last_updated = str(daily.index[-1])

    price_change = latest_price - previous_price
    price_change_percent = (
        (price_change / previous_price) * 100
        if previous_price != 0
        else 0.0
    )

    currency = "USD"
    try:
        currency = ticker.fast_info.get("currency", "USD") or "USD"
    except Exception:
        pass

    result = {
        "symbol": symbol,
        "price": round(latest_price, 2),
        "currency": currency,
        "price_change": round(price_change, 2),
        "price_change_percent": round(price_change_percent, 2),

        # Main RSI is daily RSI.
        "rsi": round(daily_rsi, 2) if daily_rsi is not None else None,
        "rsi_daily": round(daily_rsi, 2) if daily_rsi is not None else None,
        "rsi_hourly": (
            round(hourly_rsi, 2) if hourly_rsi is not None else None
        ),

        # Daily MACD.
        "macd": round(macd, 4) if macd is not None else None,
        "macd_signal": (
            round(macd_signal, 4) if macd_signal is not None else None
        ),
        "macd_histogram": (
            round(macd_histogram, 4)
            if macd_histogram is not None else None
        ),

        "relative_volatility": (
            round(relative_volatility, 4)
            if relative_volatility is not None else None
        ),
        "relative_volume": (
            round(relative_volume, 2)
            if relative_volume is not None else None
        ),

        "last_updated": last_updated,
        "daily_last_updated": str(daily.index[-1]),
        "interval": "1d",
    }

    print(f"\n[Finsight] {symbol}")
    print(f"Price: {result['price']} {currency}")
    print(f"Daily RSI (14): {result['rsi']}")
    print(f"Hourly RSI (14): {result['rsi_hourly']}")
    print(f"MACD: {result['macd']}")
    print(f"MACD signal: {result['macd_signal']}")
    print(f"MACD histogram: {result['macd_histogram']}")
    print(f"Relative volatility: {result['relative_volatility']}")
    print(f"Relative volume: {result['relative_volume']}")

    return result
