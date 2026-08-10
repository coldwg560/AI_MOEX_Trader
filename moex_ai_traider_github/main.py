#!/usr/bin/env python3
"""
main.py — Точка входа торгового бота.

Цикл:
  1. Скачать 100 часовых свечей
  2. Рассчитать индикаторы (EMA50, EMA200, RSI14, паттерны)
  3. Проверить Smart Pullback фильтр
  4. Если фильтр пройден → LLM → BUY / HOLD
  5. Проверить открытые позиции на TP/SL → автоматическая продажа
  6. Повторить через 1 час (через schedule)
"""

import logging
import sys
import time

import schedule
from t_tech.invest import CandleInterval

from config import settings
from data_fetcher import DataFetcher
from strategy import SmartPullbackStrategy
from broker import create_broker, BaseBroker

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("trading_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


# ── Глобальные объекты ───────────────────────────────────────────────────
fetcher: DataFetcher
strategy: SmartPullbackStrategy
broker: BaseBroker


def run_cycle() -> None:
    """Один торговый цикл."""
    ticker = settings.ticker

    logger.info("=" * 60)
    logger.info("🔄 Начало торгового цикла | %s | Режим: %s", ticker, settings.trading_mode)
    logger.info("=" * 60)

    # ── 1. Получение свечей ──────────────────────────────────────────
    try:
        df = fetcher.get_candles(
            ticker=ticker,
            interval=CandleInterval.CANDLE_INTERVAL_HOUR,
            count=100,
        )
    except Exception as e:
        logger.error("❌ Ошибка получения свечей: %s", e)
        return

    if df.empty:
        logger.warning("⚠ Нет данных по свечам. Рынок закрыт?")
        return

    # ── 2. Индикаторы ────────────────────────────────────────────────
    df = DataFetcher.compute_indicators(df)
    last = df.iloc[-1]
    logger.info(
        "📊 Последняя свеча: close=%.2f | EMA50=%s | EMA200=%s | RSI=%.2f",
        last["close"],
        f'{last["EMA_50"]:.2f}' if "EMA_50" in last and last["EMA_50"] == last["EMA_50"] else "N/A",
        f'{last["EMA_200"]:.2f}' if "EMA_200" in last and last["EMA_200"] == last["EMA_200"] else "N/A",
        last.get("RSI_14", 0),
    )

    # ── 3. Проверка TP/SL для открытых позиций ───────────────────────
    current_price = last["close"]
    if broker.has_position(ticker):
        tp_sl = broker.check_tp_sl(ticker, current_price)
        if tp_sl == "TP":
            logger.info("🎯 Сработал TAKE PROFIT!")
            broker.sell(ticker, current_price, reason="Take Profit")
        elif tp_sl == "SL":
            logger.info("🛑 Сработал STOP LOSS!")
            broker.sell(ticker, current_price, reason="Stop Loss")
        else:
            pos = broker.get_position(ticker)
            if pos:
                unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
                logger.info(
                    "📦 Открыта позиция: %d шт × %.2f, текущая: %.2f, PnL: %+.2f",
                    pos.quantity, pos.entry_price, current_price, unrealized_pnl,
                )

    # ── 4. Стратегия (фильтр + LLM) ─────────────────────────────────
    if broker.has_position(ticker):
        logger.info("⏸  Позиция уже открыта — пропускаем оценку для входа.")
    else:
        balance = broker.get_balance()
        decision = strategy.evaluate(ticker, df, balance)
        if decision is None:
            logger.info("⏸  Фильтр не пройден — ожидание.")
        elif decision.action == "BUY":
            # Используем количество лотов, определённое LLM
            quantity = max(1, decision.quantity)

            logger.info(
                "🟢 Покупаем %s: %d шт × %.2f | TP=%.2f | SL=%.2f",
                ticker, quantity, current_price,
                decision.take_profit, decision.stop_loss,
            )

            figi = fetcher.resolve_figi(ticker)
            success = broker.buy(
                ticker=ticker,
                figi=figi,
                price=current_price,
                quantity=quantity,
                take_profit=decision.take_profit,
                stop_loss=decision.stop_loss,
            )
            if success:
                logger.info("✅ Ордер на покупку исполнен!")
            else:
                logger.warning("⚠ Ордер на покупку не исполнен.")
        else:
            logger.info("🟡 LLM решение: HOLD — %s", decision.reason)

    # ── Статистика ───────────────────────────────────────────────────
    logger.info(
        "💼 Баланс: %.2f RUB | Открытых позиций: %d",
        broker.get_balance(),
        1 if broker.has_position(ticker) else 0,
    )
    logger.info("─" * 60)


def main() -> None:
    """Точка входа."""
    global fetcher, strategy, broker

    logger.info("🚀 Запуск торгового бота")
    logger.info("   Режим:  %s", settings.trading_mode)
    logger.info("   Тикер:  %s", settings.ticker)
    logger.info("   Тариф:  %s (%.2f%%)", settings.tariff, settings.commission_rate * 100)

    # Валидация конфига
    try:
        settings.validate()
    except ValueError as e:
        logger.critical("❌ Ошибка конфигурации: %s", e)
        sys.exit(1)

    # Инициализация компонентов
    fetcher = DataFetcher()
    strategy = SmartPullbackStrategy()
    broker = create_broker()

    # Первый запуск сразу
    logger.info("▶ Первый торговый цикл...")
    run_cycle()

    # Планировщик — каждый час
    schedule.every(1).hours.do(run_cycle)
    logger.info("⏰ Планировщик запущен: цикл каждый 1 час")

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("⏹ Бот остановлен пользователем (Ctrl+C)")
        sys.exit(0)


if __name__ == "__main__":
    main()
