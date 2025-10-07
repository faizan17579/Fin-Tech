import numpy as np
import pandas as pd


def generate_sine_series(n=200, noise=0.1, freq='D', start='2024-01-01'):
    idx = pd.date_range(start, periods=n, freq=freq)
    base = np.sin(np.linspace(0, 10, n))
    trend = np.linspace(50, 55, n)
    noise_arr = np.random.normal(scale=noise, size=n)
    y = base * 5 + trend + noise_arr
    return pd.Series(y, index=idx)


def generate_ohlcv(n=200, start_price=100.0, freq='D', start='2024-01-01'):
    idx = pd.date_range(start, periods=n, freq=freq)
    prices = [start_price]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + np.random.normal(scale=0.01)))
    prices = np.array(prices)
    opens = prices * (1 + np.random.normal(scale=0.001, size=n))
    closes = prices * (1 + np.random.normal(scale=0.001, size=n))
    highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(scale=0.002, size=n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(scale=0.002, size=n)))
    volumes = np.random.randint(1000, 2000, size=n)
    df = pd.DataFrame({
        'timestamp': idx,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes,
    })
    return df


