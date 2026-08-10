import asyncio
import logging
from typing import List, Callable, Optional
from datetime import datetime

from config import config_manager
from models import TradeAction, TradingMode, Timeframe, TradeRecord
from services.market_service import MarketService
from services.ai_service import OpenRouterTrader
from core.indicators import compute_all_indicators

logger = logging.getLogger(__name__)

class TraderBot:
    def __init__(self):
        self.is_running = False
        self.task = None
        self.logs: List[str] = []
        self.trade_history: List[TradeRecord] = []
        self.market_service = MarketService(TradingMode.VIRTUAL)
        self.on_log_callback: Optional[Callable] = None
        self.on_update_callback: Optional[Callable] = None

        self.target_ticker = "SBER.ME"

    def add_log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {msg}"
        self.logs.append(log_msg)
        logger.info(log_msg)
        if len(self.logs) > 200:
            self.logs.pop(0)
        if self.on_log_callback:
            self.on_log_callback(log_msg)

    def add_trade(self, action: str, price: float, qty: int, confidence: int, reasoning: str, indicators: str, pnl: float = 0.0):
        record = TradeRecord(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ticker=self.target_ticker,
            action=action,
            price=price,
            quantity=qty,
            confidence=confidence,
            reasoning=reasoning,
            indicators=indicators,
            pnl=pnl
        )
        self.trade_history.append(record)
        if len(self.trade_history) > 100:
            self.trade_history.pop(0)

    async def _trading_loop(self):
        self.add_log("▶ Trading bot started.")
        while self.is_running:
            settings = config_manager.settings
            if not settings.openrouter_token:
                self.add_log("⚠ Missing OpenRouter token.")
                await asyncio.sleep(5)
                continue

            ai = OpenRouterTrader(settings.openrouter_token, settings.model_name)
            timeframe = settings.timeframe

            try:
                # 1. Get market data for the configured timeframe
                self.add_log(f"📊 Fetching market data ({timeframe.value} timeframe)...")
                market_data = self.market_service.get_market_data(self.target_ticker, timeframe)
                price = market_data.get("price", 0.0)
                candles = market_data.get("candles", [])

                if price <= 0:
                    self.add_log(f"⚠ Market closed or invalid price. Retrying in 60s...")
                    await asyncio.sleep(60)
                    continue

                self.add_log(f"💰 {self.target_ticker} = {price:.2f} RUB")

                # Update positions display
                self.market_service.update_positions_prices(self.target_ticker, price)

                # 2. Compute technical indicators
                indicators = compute_all_indicators(candles) if candles else {}
                if indicators:
                    self.add_log(f"📈 RSI={indicators.get('rsi14', '?')} | SMA20={indicators.get('sma20', '?')} | SMA50={indicators.get('sma50', '?')}")

                # 3. Get AI recommendation
                portfolio = self.market_service.get_portfolio()
                positions_info = ""
                for p in portfolio["positions"]:
                    positions_info += f"  {p.name}: {p.quantity} shares @ avg {p.average_price:.2f}, PnL={p.unrealized_pnl:.2f}\n"

                self.add_log(f"🤖 Asking AI ({settings.model_name})...")
                recommendation = await ai.analyze_market(
                    ticker=self.target_ticker,
                    price=price,
                    portfolio_balance=portfolio.get("balance_rub", 0.0),
                    recent_candles=candles,
                    indicators=indicators,
                    timeframe=timeframe.value,
                    positions_info=positions_info
                )

                action_emoji = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}
                emoji = action_emoji.get(recommendation.action.value, "⚪")
                self.add_log(f"{emoji} AI Decision: {recommendation.action.value.upper()} (Confidence: {recommendation.confidence}%)")
                self.add_log(f"💡 Reasoning: {recommendation.reasoning}")
                if recommendation.indicators_used:
                    self.add_log(f"🔧 Indicators: {recommendation.indicators_used}")

                # 4. Execute trade
                quantity_to_trade = 10
                if recommendation.confidence > 70:
                    if recommendation.action == TradeAction.BUY:
                        self.add_log(f"➡ Executing PAPER BUY {quantity_to_trade} shares @ {price:.2f}...")
                        success = self.market_service.execute_trade(self.target_ticker, "buy", quantity_to_trade, price)
                        if success:
                            self.add_log("✅ BUY order filled.")
                            self.add_trade("BUY", price, quantity_to_trade, recommendation.confidence, recommendation.reasoning, recommendation.indicators_used)

                    elif recommendation.action == TradeAction.SELL:
                        self.add_log(f"➡ Executing PAPER SELL {quantity_to_trade} shares @ {price:.2f}...")
                        avg = self.market_service.positions.get(self.target_ticker)
                        realized_pnl = 0.0
                        if avg:
                            realized_pnl = (price - avg.average_price) * quantity_to_trade
                        success = self.market_service.execute_trade(self.target_ticker, "sell", quantity_to_trade, price)
                        if success:
                            self.add_log(f"✅ SELL order filled. Realized PnL: {realized_pnl:+.2f} RUB")
                            self.add_trade("SELL", price, quantity_to_trade, recommendation.confidence, recommendation.reasoning, recommendation.indicators_used, realized_pnl)
                else:
                    self.add_log(f"⏸ Confidence too low ({recommendation.confidence}%), holding.")
                    self.add_trade("HOLD", price, 0, recommendation.confidence, recommendation.reasoning, recommendation.indicators_used)

                if self.on_update_callback:
                    self.on_update_callback()

            except Exception as e:
                self.add_log(f"❌ Error: {e}")

            # Sleep based on timeframe
            sleep_map = {Timeframe.H3: 30, Timeframe.H6: 60, Timeframe.D1: 120}
            sleep_seconds = sleep_map.get(timeframe, 30)
            self.add_log(f"⏳ Next analysis in {sleep_seconds}s...")
            for _ in range(sleep_seconds):
                if not self.is_running:
                    break
                await asyncio.sleep(1)

    def start(self):
        if not self.is_running:
            self.is_running = True
            loop = asyncio.get_event_loop()
            self.task = loop.create_task(self._trading_loop())

    def stop(self):
        if self.is_running:
            self.is_running = False
            self.add_log("⏹ Trading bot stopped.")
            if self.task:
                self.task.cancel()
                self.task = None

bot = TraderBot()
