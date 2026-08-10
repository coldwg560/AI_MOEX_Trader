"""
Trading Knowledge Base — Patterns, Oscillators, and Strategies.

This module provides a comprehensive reference for the AI trader.
It is injected into the system prompt so the LLM has expert-level
context on technical analysis tools and when to use them.
"""

TRADING_KNOWLEDGE_BASE = """
# TRADING KNOWLEDGE BASE

## I. CANDLESTICK PATTERNS

### Bullish Patterns (signals to BUY)
1. **Hammer**: Small body at the top, long lower shadow (2x+ body). Appears at the bottom of a downtrend. Signals reversal upward.
2. **Morning Star**: 3-candle pattern — long red, small body (gap down), long green closing above midpoint of first candle. Strong reversal from downtrend.
3. **Bullish Engulfing**: Green candle completely engulfs previous red candle. Indicates strong buying pressure after a decline.
4. **Three White Soldiers**: Three consecutive long green candles with higher closes. Confirms strong uptrend momentum.
5. **Piercing Line**: After a red candle, a green candle opens below the previous low but closes above the midpoint of the red candle.

### Bearish Patterns (signals to SELL)
1. **Shooting Star**: Small body at the bottom, long upper shadow. Appears at the top of an uptrend. Signals reversal downward.
2. **Evening Star**: 3-candle pattern — long green, small body (gap up), long red closing below midpoint of first candle.
3. **Bearish Engulfing**: Red candle completely engulfs previous green candle. Indicates strong selling pressure.
4. **Three Black Crows**: Three consecutive long red candles with lower closes. Confirms strong downtrend.
5. **Dark Cloud Cover**: After a green candle, a red candle opens above the previous high but closes below the midpoint of the green candle.

### Continuation / Indecision
1. **Doji**: Open and close are nearly the same. Signals market indecision.
2. **Spinning Top**: Small body with roughly equal upper and lower shadows. Indecision.

---

## II. TECHNICAL INDICATORS (OSCILLATORS & MOVING AVERAGES)

### Moving Averages
1. **SMA (Simple Moving Average)**: Average price over N periods. Use SMA20 and SMA50.
   - **Golden Cross**: SMA20 crosses ABOVE SMA50 → Bullish BUY signal.
   - **Death Cross**: SMA20 crosses BELOW SMA50 → Bearish SELL signal.
2. **EMA (Exponential Moving Average)**: Gives more weight to recent prices. More responsive than SMA.
   - EMA12 and EMA26 are commonly used together.

### Oscillators
1. **RSI (Relative Strength Index)**: Measures momentum on a 0-100 scale.
   - RSI > 70 → **Overbought** → potential SELL signal.
   - RSI < 30 → **Oversold** → potential BUY signal.
   - RSI between 40-60 → Neutral / HOLD.
2. **MACD (Moving Average Convergence Divergence)**:
   - MACD Line = EMA12 - EMA26.
   - Signal Line = EMA9 of MACD Line.
   - **Bullish crossover**: MACD crosses above Signal → BUY.
   - **Bearish crossover**: MACD crosses below Signal → SELL.
   - **Divergence**: Price makes new high but MACD doesn't → reversal likely.
3. **Stochastic Oscillator**: Compares closing price to price range over N periods (0-100).
   - %K > 80 → Overbought → SELL.
   - %K < 20 → Oversold → BUY.
   - %K crossing %D from below → BUY signal.
4. **Bollinger Bands**: SMA20 ± 2 standard deviations.
   - Price touching upper band → Overbought.
   - Price touching lower band → Oversold.
   - Band squeeze (narrowing) → Breakout imminent.

### Volume Indicators
1. **OBV (On Balance Volume)**: Cumulative volume indicator.
   - Rising OBV with rising price → Trend confirmed.
   - Divergence between OBV and price → Trend weakening.
2. **VWAP (Volume Weighted Average Price)**: Average price weighted by volume.
   - Price > VWAP → Bullish bias.
   - Price < VWAP → Bearish bias.

---

## III. TRADING STRATEGIES

### Strategy 1: Trend Following
- Use SMA20/SMA50 crossover to determine trend direction.
- Confirm with MACD crossover.
- Enter on pullbacks to SMA20 in the direction of the trend.
- Stop loss below recent swing low (for longs).

### Strategy 2: Mean Reversion
- When RSI < 30 AND price touches lower Bollinger Band → BUY.
- When RSI > 70 AND price touches upper Bollinger Band → SELL.
- Best used in ranging (non-trending) markets.

### Strategy 3: Breakout Trading
- Identify consolidation zones (Bollinger Band squeeze).
- Enter when price breaks above resistance with high volume (OBV confirming).
- Stop loss inside the consolidation zone.

### Strategy 4: Multi-Timeframe Confirmation
- Use the higher timeframe to determine trend (e.g., 1D for direction).
- Use the lower timeframe for entry timing (e.g., 3H for entry signal).
- Only take trades in the direction of the higher timeframe trend.

---

## IV. RISK MANAGEMENT RULES

1. **Position Sizing**: Never risk more than 2-5% of portfolio on a single trade.
2. **Stop Loss**: Always define a stop loss level before entering a trade.
3. **Take Profit**: Use 2:1 or 3:1 reward-to-risk ratio.
4. **Diversification**: Don't allocate more than 20% of portfolio to one asset.
5. **Confidence Threshold**: Only execute trades with confidence > 70%.
"""

def get_knowledge_base() -> str:
    """Returns the full trading knowledge base as a string for AI context."""
    return TRADING_KNOWLEDGE_BASE
