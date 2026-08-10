from pydantic import BaseModel
from enum import Enum
from typing import List, Optional
from datetime import datetime

class TradingMode(str, Enum):
    VIRTUAL = "virtual"
    REAL = "real"

class Timeframe(str, Enum):
    H3 = "3h"
    H6 = "6h"
    D1 = "1d"

class SettingsModel(BaseModel):
    openrouter_token: str = ""
    model_name: str = "openai/gpt-4o-mini"
    trading_mode: TradingMode = TradingMode.VIRTUAL
    timeframe: Timeframe = Timeframe.H3

class TradeAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

class AIRecommendation(BaseModel):
    action: TradeAction
    confidence: int  # 0 to 100
    reasoning: str
    target_ticker: str
    indicators_used: str = ""

class PositionModel(BaseModel):
    ticker: str
    name: str
    quantity: int
    average_price: float
    current_price: float
    unrealized_pnl: float

class TradeRecord(BaseModel):
    timestamp: str
    ticker: str
    action: str  # BUY / SELL / HOLD
    price: float
    quantity: int
    confidence: int
    reasoning: str
    indicators: str
    pnl: float = 0.0  # realized PnL for sells
