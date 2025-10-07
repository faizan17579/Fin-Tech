from __future__ import annotations

from typing import List


def naive_forecast(prices: List[float], horizon: int) -> List[float]:
    if not prices:
        return [0.0 for _ in range(horizon)]
    last = prices[-1]
    return [float(last) for _ in range(horizon)]


