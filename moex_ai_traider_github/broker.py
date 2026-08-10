"""
broker.py — Исполнение сделок: PaperBroker (симуляция) и LiveBroker (реальные ордера).

Паттерн Strategy / Factory — переключение через TRADING_MODE.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from t_tech.invest import (
    Client,
    OrderDirection,
    OrderType,
    StopOrderDirection,
    StopOrderExpirationType,
    StopOrderType,
)
from t_tech.invest.utils import decimal_to_quotation, quotation_to_decimal

from config import settings, SLIPPAGE_PCT

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Модель позиции
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Position:
    """Открытая позиция."""
    ticker: str
    figi: str
    quantity: int
    entry_price: float        # средняя цена входа (с учётом slippage)
    take_profit: float         # целевая цена TP
    stop_loss: float           # цена SL
    opened_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# ═══════════════════════════════════════════════════════════════════════════
# Абстрактный базовый брокер
# ═══════════════════════════════════════════════════════════════════════════

class BaseBroker(ABC):
    """Абстрактный интерфейс исполнения сделок."""

    @abstractmethod
    def buy(self, ticker: str, figi: str, price: float, quantity: int,
            take_profit: float, stop_loss: float) -> bool:
        """Купить `quantity` лотов по `price`."""
        ...

    @abstractmethod
    def sell(self, ticker: str, price: float, reason: str) -> bool:
        """Продать открытую позицию по `price`."""
        ...

    @abstractmethod
    def move_stop(self, ticker: str, new_stop: float) -> bool:
        """Переместить стоп-лосс на новый уровень."""
        ...

    @abstractmethod
    def check_tp_sl(self, ticker: str, current_price: float) -> Optional[str]:
        """
        Проверяет TP/SL для открытой позиции.
        Возвращает 'TP', 'SL' или None.
        """
        ...

    @abstractmethod
    def get_balance(self) -> float:
        """Текущий доступный баланс (RUB)."""
        ...

    @abstractmethod
    def get_position(self, ticker: str) -> Optional[Position]:
        """Текущая открытая позиция по тикеру."""
        ...

    @abstractmethod
    def has_position(self, ticker: str) -> bool:
        """Есть ли открытая позиция."""
        ...


# ═══════════════════════════════════════════════════════════════════════════
# PAPER BROKER
# ═══════════════════════════════════════════════════════════════════════════

class PaperBroker(BaseBroker):
    """
    Виртуальный брокер для paper trading.

    - Виртуальный баланс
    - Комиссии по тарифу (при покупке И при продаже)
    - Проскальзывание ±0.02%
    """

    def __init__(self, initial_balance: float | None = None):
        self.balance = initial_balance or settings.paper_balance
        self.positions: dict[str, Position] = {}
        self.trade_log: list[dict] = []
        self.total_commission: float = 0.0

        logger.info(
            "📝 PaperBroker инициализирован | Баланс: %.2f RUB | Тариф: %s (%.2f%%)",
            self.balance, settings.tariff, settings.commission_rate * 100,
        )

    def buy(self, ticker: str, figi: str, price: float, quantity: int,
            take_profit: float, stop_loss: float) -> bool:

        # Проскальзывание: цена покупки чуть выше
        exec_price = price * (1 + SLIPPAGE_PCT)
        cost = exec_price * quantity

        # Комиссия
        commission = cost * settings.commission_rate
        total_cost = cost + commission

        if total_cost > self.balance:
            logger.warning(
                "❌ Недостаточно средств: нужно %.2f, доступно %.2f",
                total_cost, self.balance,
            )
            return False

        self.balance -= total_cost
        self.total_commission += commission

        self.positions[ticker] = Position(
            ticker=ticker,
            figi=figi,
            quantity=quantity,
            entry_price=exec_price,
            take_profit=take_profit,
            stop_loss=stop_loss,
        )

        trade = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": "BUY",
            "ticker": ticker,
            "price": round(exec_price, 2),
            "quantity": quantity,
            "commission": round(commission, 2),
            "balance_after": round(self.balance, 2),
        }
        self.trade_log.append(trade)

        logger.info(
            "🟢 PAPER BUY %s | %d шт × %.2f = %.2f | Комиссия: %.2f | "
            "TP=%.2f | SL=%.2f | Баланс: %.2f",
            ticker, quantity, exec_price, cost, commission,
            take_profit, stop_loss, self.balance,
        )
        return True

    def sell(self, ticker: str, price: float, reason: str) -> bool:
        pos = self.positions.get(ticker)
        if not pos:
            logger.warning("❌ Нет открытой позиции по %s для продажи", ticker)
            return False

        # Проскальзывание: цена продажи чуть ниже
        exec_price = price * (1 - SLIPPAGE_PCT)
        revenue = exec_price * pos.quantity

        # Комиссия при продаже
        commission = revenue * settings.commission_rate
        net_revenue = revenue - commission

        self.balance += net_revenue
        self.total_commission += commission

        # P&L
        pnl = (exec_price - pos.entry_price) * pos.quantity - commission
        # Вычитаем комиссию на покупку тоже (уже была списана, но для P&L учитываем)
        buy_commission = pos.entry_price * pos.quantity * settings.commission_rate
        total_pnl = pnl - buy_commission

        trade = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": "SELL",
            "ticker": ticker,
            "price": round(exec_price, 2),
            "quantity": pos.quantity,
            "commission": round(commission, 2),
            "pnl": round(total_pnl, 2),
            "reason": reason,
            "balance_after": round(self.balance, 2),
        }
        self.trade_log.append(trade)

        del self.positions[ticker]

        logger.info(
            "🔴 PAPER SELL %s | %d шт × %.2f | Комиссия: %.2f | PnL: %+.2f | "
            "Причина: %s | Баланс: %.2f",
            ticker, pos.quantity, exec_price, commission, total_pnl,
            reason, self.balance,
        )
        return True

    def move_stop(self, ticker: str, new_stop: float) -> bool:
        pos = self.positions.get(ticker)
        if not pos:
            return False
        pos.stop_loss = new_stop
        logger.info("🛡 PAPER MOVE_STOP %s -> %.2f", ticker, new_stop)
        return True

    def check_tp_sl(self, ticker: str, current_price: float) -> Optional[str]:
        pos = self.positions.get(ticker)
        if not pos:
            return None

        if current_price >= pos.take_profit > 0:
            return "TP"
        if 0 < pos.stop_loss >= current_price:
            return "SL"
        return None

    def get_balance(self) -> float:
        return self.balance

    def get_position(self, ticker: str) -> Optional[Position]:
        return self.positions.get(ticker)

    def has_position(self, ticker: str) -> bool:
        return ticker in self.positions


# ═══════════════════════════════════════════════════════════════════════════
# LIVE BROKER
# ═══════════════════════════════════════════════════════════════════════════

class LiveBroker(BaseBroker):
    """
    Реальный брокер через Tinkoff Invest API.

    - Рыночные ордера через OrdersService
    - Стоп-ордера (TP/SL) через StopOrdersService
    - Проверка баланса перед покупкой
    """

    def __init__(self):
        self.token = settings.tinkoff_token
        self.account_id = settings.tinkoff_account_id
        self.positions: dict[str, Position] = {}

        logger.info(
            "💰 LiveBroker инициализирован | Account: %s",
            self.account_id,
        )

    def _get_rub_balance(self) -> float:
        """Получает доступный баланс RUB через API."""
        try:
            with Client(self.token) as client:
                portfolio = client.operations.get_portfolio(account_id=self.account_id)
                if hasattr(portfolio, 'total_amount_currencies') and portfolio.total_amount_currencies:
                    return float(quotation_to_decimal(portfolio.total_amount_currencies))

                # Альтернатива — через portfolio
                total = float(quotation_to_decimal(portfolio.total_amount_portfolio))
                return total
        except Exception as e:
            logger.error("❌ LIVE _get_rub_balance ошибка: %s", e)
            return 0.0

    def buy(self, ticker: str, figi: str, price: float, quantity: int,
            take_profit: float, stop_loss: float) -> bool:

        cost = price * quantity

        # Проверяем баланс
        balance = self._get_rub_balance()
        if cost > balance:
            logger.warning(
                "❌ LIVE: Недостаточно средств: нужно %.2f, доступно %.2f",
                cost, balance,
            )
            return False

        try:
            with Client(self.token) as client:
                # Рыночный ордер на покупку
                order = client.orders.post_order(
                    figi=figi,
                    quantity=quantity,
                    direction=OrderDirection.ORDER_DIRECTION_BUY,
                    account_id=self.account_id,
                    order_type=OrderType.ORDER_TYPE_MARKET,
                )
                order_id = order.order_id
                logger.info("🟢 LIVE BUY ордер размещён: %s (order_id=%s)", ticker, order_id)

                # Выставляем стоп-лосс
                if stop_loss > 0:
                    client.stop_orders.post_stop_order(
                        figi=figi,
                        quantity=quantity,
                        stop_price=decimal_to_quotation(stop_loss),
                        direction=StopOrderDirection.STOP_ORDER_DIRECTION_SELL,
                        account_id=self.account_id,
                        expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL,
                        stop_order_type=StopOrderType.STOP_ORDER_TYPE_STOP_LOSS,
                    )
                    logger.info("🛡  Стоп-лосс выставлен: %.2f", stop_loss)

                # Выставляем тейк-профит
                if take_profit > 0:
                    client.stop_orders.post_stop_order(
                        figi=figi,
                        quantity=quantity,
                        stop_price=decimal_to_quotation(take_profit),
                        direction=StopOrderDirection.STOP_ORDER_DIRECTION_SELL,
                        account_id=self.account_id,
                        expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL,
                        stop_order_type=StopOrderType.STOP_ORDER_TYPE_TAKE_PROFIT,
                    )
                    logger.info("🎯 Тейк-профит выставлен: %.2f", take_profit)

            # Сохраняем позицию локально
            self.positions[ticker] = Position(
                ticker=ticker,
                figi=figi,
                quantity=quantity,
                entry_price=price,
                take_profit=take_profit,
                stop_loss=stop_loss,
            )

            return True

        except Exception as e:
            logger.error("❌ LIVE BUY ошибка: %s", e)
            return False

    def sell(self, ticker: str, price: float, reason: str) -> bool:
        pos = self.positions.get(ticker)
        if not pos:
            logger.warning("❌ LIVE: Нет позиции по %s", ticker)
            return False

        try:
            with Client(self.token) as client:
                order = client.orders.post_order(
                    figi=pos.figi,
                    quantity=pos.quantity,
                    direction=OrderDirection.ORDER_DIRECTION_SELL,
                    account_id=self.account_id,
                    order_type=OrderType.ORDER_TYPE_MARKET,
                )
                logger.info(
                    "🔴 LIVE SELL ордер: %s (order_id=%s, reason=%s)",
                    ticker, order.order_id, reason,
                )

                # Отменяем все стоп-ордера по FIGI
                stop_orders = client.stop_orders.get_stop_orders(
                    account_id=self.account_id
                )
                for so in stop_orders.stop_orders:
                    if so.figi == pos.figi:
                        client.stop_orders.cancel_stop_order(
                            stop_order_id=so.stop_order_id
                        )
                        logger.info("  🗑 Стоп-ордер %s отменён", so.stop_order_id)

            del self.positions[ticker]
            return True

        except Exception as e:
            logger.error("❌ LIVE SELL ошибка: %s", e)
            return False

    def move_stop(self, ticker: str, new_stop: float) -> bool:
        pos = self.positions.get(ticker)
        if not pos:
            return False
        try:
            with Client(self.token) as client:
                # Cancel old STOP_LOSS
                stop_orders = client.stop_orders.get_stop_orders(account_id=self.account_id)
                for so in stop_orders.stop_orders:
                    if so.figi == pos.figi and so.stop_order_type == StopOrderType.STOP_ORDER_TYPE_STOP_LOSS:
                        client.stop_orders.cancel_stop_order(stop_order_id=so.stop_order_id)
                        logger.info("  🗑 LIVE MOVE_STOP: Старый SL %s отменён (%s)", so.stop_order_id, ticker)
                
                # Setup new STOP_LOSS
                client.stop_orders.post_stop_order(
                    figi=pos.figi,
                    quantity=pos.quantity,
                    stop_price=decimal_to_quotation(new_stop),
                    direction=StopOrderDirection.STOP_ORDER_DIRECTION_SELL,
                    account_id=self.account_id,
                    expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL,
                    stop_order_type=StopOrderType.STOP_ORDER_TYPE_STOP_LOSS,
                )
            pos.stop_loss = new_stop
            logger.info("🛡 LIVE MOVE_STOP %s -> %.2f", ticker, new_stop)
            return True
        except Exception as e:
            logger.error("❌ LIVE MOVE_STOP ошибка: %s", e)
            return False

    def check_tp_sl(self, ticker: str, current_price: float) -> Optional[str]:
        """
        В LIVE режиме TP/SL обрабатываются стоп-ордерами на бирже.
        Этот метод — для мониторинга / логирования.
        """
        pos = self.positions.get(ticker)
        if not pos:
            return None

        if current_price >= pos.take_profit > 0:
            return "TP"
        if 0 < pos.stop_loss >= current_price:
            return "SL"
        return None

    def get_balance(self) -> float:
        return self._get_rub_balance()

    def get_position(self, ticker: str) -> Optional[Position]:
        return self.positions.get(ticker)

    def has_position(self, ticker: str) -> bool:
        return ticker in self.positions


# ═══════════════════════════════════════════════════════════════════════════
# FACTORY
# ═══════════════════════════════════════════════════════════════════════════

def create_broker(mode: str | None = None) -> BaseBroker:
    """
    Фабрика брокеров.

    Args:
        mode: "PAPER" или "LIVE". По умолчанию берётся из settings.
    """
    mode = (mode or settings.trading_mode).upper()

    if mode == "PAPER":
        return PaperBroker()
    elif mode == "LIVE":
        return LiveBroker()
    else:
        raise ValueError(f"Неизвестный TRADING_MODE: {mode}. Допустимо: PAPER, LIVE")
