import logging
from typing import Dict, Any, List
import yfinance as yf
from models import TradingMode, PositionModel, Timeframe

logger = logging.getLogger(__name__)

# Map our Timeframe enum to yfinance parameters
TIMEFRAME_CONFIG = {
    Timeframe.H3: {"period": "1mo", "interval": "1h", "label": "3 Hours"},
    Timeframe.H6: {"period": "3mo", "interval": "1h", "label": "6 Hours"},
    Timeframe.D1: {"period": "6mo", "interval": "1d", "label": "1 Day"},
}

class MarketService:
    def __init__(self, mode: TradingMode):
        self.mode = mode
        self.balance_rub = 100000.0
        self.positions: Dict[str, PositionModel] = {}

    def get_portfolio(self) -> Dict[str, Any]:
        return {
            "balance_rub": self.balance_rub,
            "positions": list(self.positions.values())
        }

    def get_market_data(self, ticker: str, timeframe: Timeframe = Timeframe.H3) -> Dict[str, Any]:
        """Gets price and candles for the specified timeframe."""
        try:
            config = TIMEFRAME_CONFIG[timeframe]
            stock = yf.Ticker(ticker)
            hist = stock.history(period=config["period"], interval=config["interval"])

            if hist.empty:
                return {"price": 0.0, "candles": []}

            price = float(hist['Close'].iloc[-1])

            candles = []
            for date, row in hist.iterrows():
                candles.append({
                    "date": str(date),
                    "open": round(float(row['Open']), 2),
                    "high": round(float(row['High']), 2),
                    "low": round(float(row['Low']), 2),
                    "close": round(float(row['Close']), 2),
                    "volume": int(row['Volume'])
                })

            return {"price": price, "candles": candles}
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return {"price": 0.0, "candles": []}

    def execute_trade(self, ticker: str, action: str, quantity: int, current_price: float) -> bool:
        cost = current_price * quantity

        if action == "buy":
            if self.balance_rub >= cost:
                self.balance_rub -= cost
                if ticker in self.positions:
                    pos = self.positions[ticker]
                    total_spent = (pos.average_price * pos.quantity) + cost
                    pos.quantity += quantity
                    pos.average_price = total_spent / pos.quantity
                else:
                    self.positions[ticker] = PositionModel(
                        ticker=ticker,
                        name=ticker.split(".")[0],
                        quantity=quantity,
                        average_price=current_price,
                        current_price=current_price,
                        unrealized_pnl=0.0
                    )
                return True
            else:
                logger.warning("Insufficient funds for buy.")
                return False

        elif action == "sell":
            if ticker in self.positions and self.positions[ticker].quantity >= quantity:
                self.balance_rub += cost
                pos = self.positions[ticker]
                pos.quantity -= quantity
                if pos.quantity == 0:
                    del self.positions[ticker]
                return True
            else:
                logger.warning("Insufficient quantity for sell.")
                return False

        return False

    def update_positions_prices(self, ticker: str, current_price: float):
        if ticker in self.positions:
            pos = self.positions[ticker]
            pos.current_price = current_price
            pos.unrealized_pnl = (current_price - pos.average_price) * pos.quantity
