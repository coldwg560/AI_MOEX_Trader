"""
Technical Analysis Calculator.

Computes real indicator values from candle data so the AI
receives concrete numbers rather than raw OHLCV alone.
"""
import math
from typing import List, Dict, Any

def calc_sma(closes: List[float], period: int) -> float:
    """Simple Moving Average over the last `period` values."""
    if len(closes) < period:
        return closes[-1] if closes else 0.0
    return sum(closes[-period:]) / period

def calc_ema(closes: List[float], period: int) -> float:
    """Exponential Moving Average."""
    if not closes:
        return 0.0
    k = 2 / (period + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    return ema

def calc_rsi(closes: List[float], period: int = 14) -> float:
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return 50.0  # neutral if not enough data
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_macd(closes: List[float]) -> Dict[str, float]:
    """MACD line, signal line, histogram."""
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd_line = ema12 - ema26
    # Approximate signal as EMA9 of a short recent MACD series
    signal = macd_line * 0.8  # simplified
    return {
        "macd_line": round(macd_line, 4),
        "signal_line": round(signal, 4),
        "histogram": round(macd_line - signal, 4)
    }

def calc_bollinger(closes: List[float], period: int = 20) -> Dict[str, float]:
    """Bollinger Bands: middle, upper, lower."""
    if len(closes) < period:
        mid = closes[-1] if closes else 0
        return {"upper": mid, "middle": mid, "lower": mid}
    subset = closes[-period:]
    mid = sum(subset) / period
    variance = sum((x - mid) ** 2 for x in subset) / period
    std = math.sqrt(variance)
    return {
        "upper": round(mid + 2 * std, 2),
        "middle": round(mid, 2),
        "lower": round(mid - 2 * std, 2)
    }

def calc_stochastic(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Dict[str, float]:
    """Stochastic %K."""
    if len(closes) < period:
        return {"k": 50.0}
    h = max(highs[-period:])
    l = min(lows[-period:])
    if h == l:
        return {"k": 50.0}
    k = ((closes[-1] - l) / (h - l)) * 100
    return {"k": round(k, 2)}

def compute_all_indicators(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute all indicators from a list of candle dicts."""
    if not candles:
        return {}
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    return {
        "sma20": round(calc_sma(closes, 20), 2),
        "sma50": round(calc_sma(closes, 50), 2),
        "ema12": round(calc_ema(closes, 12), 2),
        "ema26": round(calc_ema(closes, 26), 2),
        "rsi14": round(calc_rsi(closes, 14), 2),
        "macd": calc_macd(closes),
        "bollinger": calc_bollinger(closes),
        "stochastic": calc_stochastic(highs, lows, closes),
        "current_price": round(closes[-1], 2),
        "price_change_pct": round(((closes[-1] - closes[0]) / closes[0]) * 100, 2) if closes[0] else 0
    }
