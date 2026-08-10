"""
bot_engine.py — Ядро торгового бота.

Работает как фоновый движок, управляемый из GUI.
Поддерживает несколько тикеров параллельно.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Callable

from t_tech.invest import CandleInterval

from config import settings
from data_fetcher import DataFetcher
from strategy import SmartPullbackStrategy, LLMDecision
from broker import PaperBroker, LiveBroker, BaseBroker, create_broker

logger = logging.getLogger(__name__)


@dataclass
class CycleResult:
    """Результат одного торгового цикла для одного тикера."""
    timestamp: str
    ticker: str
    close: float = 0
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    rsi: Optional[float] = None
    patterns_str: str = ""
    filter_passed: bool = False
    llm_decision: Optional[str] = None
    llm_reason: str = ""
    take_profit: float = 0
    stop_loss: float = 0
    action_taken: str = ""  # BUY, SELL_TP, SELL_SL, HOLD, SKIP, ERROR
    error: str = ""


class BotEngine:
    """Торговый движок — управляет циклами анализа и сделками."""

    def __init__(self):
        self.is_running = False
        self._force_cycle = False
        self._thread: Optional[threading.Thread] = None

        # Components — created on start
        self.fetcher: Optional[DataFetcher] = None
        self.strategy: Optional[SmartPullbackStrategy] = None
        self.broker: Optional[BaseBroker] = None

        # State
        self.logs: List[str] = []
        self.total_logs_emitted: int = 0
        self.cycle_results: List[CycleResult] = []
        self.last_cycle_time: str = "—"
        self.cycles_completed: int = 0
        self.trade_history: dict[str, list[dict]] = {}

        # Callbacks
        self.on_log: Optional[Callable[[str], None]] = None

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.logs.append(line)
        self.total_logs_emitted += 1
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        logger.info(msg)
        if self.on_log:
            try:
                self.on_log(line)
            except Exception:
                pass

    def start(self):
        if self.is_running:
            return

        settings.validate()

        self.fetcher = DataFetcher()
        self.strategy = SmartPullbackStrategy()
        self.broker = create_broker()

        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._log("🚀 Бот запущен")

    def stop(self):
        if self.is_running:
            self.is_running = False
            self._log("⏹ Бот остановлен")

    def _run_loop(self):
        """Основной цикл бота."""
        while self.is_running:
            self._log("=" * 50)
            self._log(f"🔄 Торговый цикл #{self.cycles_completed + 1} | "
                      f"Тикеры: {', '.join(settings.tickers)}")
            self._log("=" * 50)

            if self.broker:
                self.monitor_portfolio()

            for ticker in settings.tickers:
                if not self.is_running:
                    break
                try:
                    result = self._process_ticker(ticker)
                    self.cycle_results.append(result)
                    if len(self.cycle_results) > 500:
                        self.cycle_results = self.cycle_results[-300:]
                except Exception as e:
                    self._log(f"❌ Ошибка {ticker}: {e}")

            self.cycles_completed += 1
            self.last_cycle_time = datetime.now().strftime("%H:%M:%S")

            # Balance report
            if self.broker:
                self._log(f"💼 Баланс: {self.broker.get_balance():,.2f} ₽")

            self._log(f"⏳ Следующий цикл через 60 мин...")

            # Sleep 1 hour (interruptible)
            for _ in range(3600):
                if not self.is_running or self._force_cycle:
                    break
                time.sleep(1)
            self._force_cycle = False

    def force_cycle(self):
        if self.is_running:
            self._force_cycle = True
            self._log("⚡ЗАПУСК ВНЕПЛАНОВОГО ОБНОВЛЕНИЯ ПО ТРЕБОВАНИЮ ПОЛЬЗОВАТЕЛЯ⚡")
        else:
            self._log("⚠ Невозможно обновить данные: Бот остановлен.")

    def monitor_portfolio(self):
        self._log("🔍 MONITOR: Проверка открытых позиций...")
        # broker.positions might be mutated, so we use list(values)
        if not hasattr(self.broker, 'positions'):
            return
            
        positions = list(self.broker.positions.values())
        if not positions:
            self._log("🔍 MONITOR: Нет открытых позиций.")
            return

        for pos in positions:
            if not self.is_running:
                break
            ticker = pos.ticker
            try:
                df = self.fetcher.get_candles(
                    ticker=ticker,
                    interval=CandleInterval.CANDLE_INTERVAL_HOUR,
                    count=100,
                )
                if df.empty:
                    continue
                    
                df = DataFetcher.compute_indicators(df)
                last = df.iloc[-1]
                current_price = float(last["close"])
                
                # PnL in percent
                pnl_percent = ((current_price - pos.entry_price) / pos.entry_price) * 100 if pos.entry_price > 0 else 0
                
                prompt = self.strategy.build_monitoring_prompt(
                    ticker=ticker,
                    df=df,
                    entry_price=pos.entry_price,
                    current_price=current_price,
                    pnl_percent=pnl_percent,
                    tp=pos.take_profit,
                    sl=pos.stop_loss
                )
                
                decision = self.strategy.ask_monitoring_llm(prompt)
                action = decision.get("action", "HOLD").upper()
                reason = decision.get("reason", "")
                
                self._log(f"🧠 ПОЗИЦИЯ {ticker}: LLM -> {action} | Причина: {reason}")
                
                if action == "SELL_NOW":
                    self.broker.sell(ticker, current_price, reason=f"LLM SELL_NOW: {reason}")
                    self.trade_history.setdefault(ticker, []).append({
                        "action": "SELL",
                        "reason": f"LLM SELL_NOW",
                        "price": current_price,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                elif action == "MOVE_STOP":
                    if pnl_percent > 2.0 and pos.stop_loss < pos.entry_price:
                        self.broker.move_stop(ticker, pos.entry_price)
            except Exception as e:
                self._log(f"❌ Ошибка мониторинга по {ticker}: {e}")

    def _process_ticker(self, ticker: str) -> CycleResult:
        """Обработка одного тикера."""
        result = CycleResult(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ticker=ticker,
        )

        self._log(f"📊 {ticker}: Загрузка свечей...")

        # 1. Get candles
        try:
            df = self.fetcher.get_candles(
                ticker=ticker,
                interval=CandleInterval.CANDLE_INTERVAL_HOUR,
                count=100,
            )
        except Exception as e:
            result.error = str(e)
            result.action_taken = "ERROR"
            self._log(f"❌ {ticker}: Ошибка загрузки свечей: {e}")
            return result

        if df.empty:
            result.action_taken = "SKIP"
            self._log(f"⚠ {ticker}: Нет данных (рынок закрыт?)")
            return result

        # 2. Compute indicators
        df = DataFetcher.compute_indicators(df)
        last = df.iloc[-1]

        result.close = float(last["close"])
        result.ema50 = float(last["EMA_50"]) if "EMA_50" in last and last["EMA_50"] == last["EMA_50"] else None
        result.ema200 = float(last["EMA_200"]) if "EMA_200" in last and last["EMA_200"] == last["EMA_200"] else None
        result.rsi = float(last["RSI_14"]) if "RSI_14" in last and last["RSI_14"] == last["RSI_14"] else None

        active_pats = []
        for col in df.columns:
            if col.startswith("CDL_") or col.startswith("GAP_"):
                val = last.get(col, 0)
                if val != 0:
                    short_name = col.replace("CDL_", "").replace("GAP_", "GAP").capitalize()
                    active_pats.append(f"[green]{short_name}[/]" if val > 0 else f"[red]{short_name}[/]")
        result.patterns_str = " ".join(active_pats)

        self._log(
            f"📈 {ticker}: close={result.close:.2f} | "
            f"EMA50={'%.2f' % result.ema50 if result.ema50 else 'N/A'} | "
            f"EMA200={'%.2f' % result.ema200 if result.ema200 else 'N/A'} | "
            f"RSI={'%.1f' % result.rsi if result.rsi else 'N/A'} | Pats: {result.patterns_str}"
        )

        # 3. Check TP/SL for existing positions
        if self.broker.has_position(ticker):
            tp_sl = self.broker.check_tp_sl(ticker, result.close)
            if tp_sl == "TP":
                self._log(f"🎯 {ticker}: TAKE PROFIT сработал!")
                self.broker.sell(ticker, result.close, "Take Profit")
                self.trade_history.setdefault(ticker, []).append({
                    "action": "SELL", "reason": "Take Profit",
                    "price": result.close, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                result.action_taken = "SELL_TP"
                return result
            elif tp_sl == "SL":
                self._log(f"🛑 {ticker}: STOP LOSS сработал!")
                self.broker.sell(ticker, result.close, "Stop Loss")
                self.trade_history.setdefault(ticker, []).append({
                    "action": "SELL", "reason": "Stop Loss",
                    "price": result.close, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                result.action_taken = "SELL_SL"
                return result
            else:
                pos = self.broker.get_position(ticker)
                pnl = (result.close - pos.entry_price) * pos.quantity
                self._log(f"📦 {ticker}: Позиция открыта ({pos.quantity} шт), PnL: {pnl:+.2f} ₽")
                result.action_taken = "HOLD_POSITION"
                return result

        # 4. Strategy filter + LLM
        result.filter_passed = self.strategy.check_filter(df)

        if not result.filter_passed:
            result.action_taken = "SKIP"
            self._log(f"⏸ {ticker}: Фильтр не пройден — пропуск")
            return result

        self._log(f"✅ {ticker}: Фильтр пройден! Запрос к LLM...")

        # LLM decision
        balance = self.broker.get_balance() if self.broker else 0.0
        allocated_budget = balance * settings.trade_allocation_pct * 0.99
        trade_history = self.trade_history.get(ticker, [])

        prompt = self.strategy.build_prompt(ticker, df, allocated_budget, trade_history)
        decision = self.strategy.ask_llm(prompt)
        result.llm_decision = decision.action
        result.llm_reason = decision.reason
        result.take_profit = decision.take_profit
        result.stop_loss = decision.stop_loss

        if decision.action == "BUY":
            quantity = max(1, decision.quantity)
            figi = self.fetcher.resolve_figi(ticker)

            self._log(
                f"🟢 {ticker}: LLM → BUY | {quantity} шт × {result.close:.2f} | "
                f"TP={decision.take_profit:.2f} | SL={decision.stop_loss:.2f}"
            )
            self._log(f"💡 {ticker}: {decision.reason}")

            ok = self.broker.buy(
                ticker=ticker, figi=figi,
                price=result.close, quantity=quantity,
                take_profit=decision.take_profit,
                stop_loss=decision.stop_loss,
            )
            result.action_taken = "BUY" if ok else "BUY_FAILED"
        else:
            result.action_taken = "HOLD"
            self._log(f"🟡 {ticker}: LLM → HOLD | {decision.reason}")

        return result


# Singleton
engine = BotEngine()
