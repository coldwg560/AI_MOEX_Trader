"""
config.py — Централизованная конфигурация бота.

Загружает все параметры из .env файла через python-dotenv.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

# Загрузка .env из корня проекта
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)


# ── Тарифные комиссии Т-Инвестиций ──────────────────────────────────────────
TARIFF_COMMISSIONS: Dict[str, float] = {
    "investor": 0.003,   # 0.3 %
    "trader":   0.0005,  # 0.05 %
}

# Проскальзывание (slippage)
SLIPPAGE_PCT: float = 0.0002  # 0.02 %


@dataclass
class Settings:
    """Mutable settings — can be changed from GUI at runtime."""

    # Tinkoff
    tinkoff_token: str = os.getenv("TINKOFF_TOKEN", "")
    tinkoff_account_id: str = os.getenv("TINKOFF_ACCOUNT_ID", "")

    # Trading
    trading_mode: str = os.getenv("TRADING_MODE", "PAPER").upper()

    # Tickers (comma-separated in env)
    tickers: List[str] = field(default_factory=lambda: [
        t.strip() for t in os.getenv("TICKERS", "SBER").split(",") if t.strip()
    ])

    # LLM
    llm_api_url: str = os.getenv("LLM_API_URL", "https://openrouter.ai/api/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek/deepseek-v3.2")
    user_strategy: str = os.getenv("USER_STRATEGY", "Я ищу фигуры разворота: Голова и плечи (3 пика, средний выше), Двойная/Тройная вершина/дно, Клин, Бриллиант, Закругленное дно, V-образный разворот.\nИ фигуры продолжения: Флаг, Вымпел, Треугольники (восходящий/нисходящий/симметричный), Прямоугольник, Чашка с ручкой.\nТебе даны последние экстремумы (Пики и Дно). Попробуй 'увидеть' в них геометрические фигуры, сведя их со свечными паттернами на текущей цене.\n- Если видишь сильный паттерн (Пинбар/Молот у Дна, Поглощение от EMA200, Двойное дно) — BUY с целью (TP) и защитой (SL).\n- Если цена висит в воздухе — HOLD.\n- Если актив только что был закрыт по Stop-Loss, входить повторно в лонг КРАЙНЕ РИСКОВАННО — почти всегда отвечай HOLD, если только нет 100% уверенности в ложном пробое.")

    # Broker
    tariff: str = os.getenv("TARIFF", "investor").lower()
    paper_balance: float = float(os.getenv("PAPER_BALANCE", "100000"))
    trade_allocation_pct: float = float(os.getenv("TRADE_ALLOCATION_PCT", "0.2"))

    @property
    def commission_rate(self) -> float:
        return TARIFF_COMMISSIONS.get(self.tariff, 0.003)

    def validate(self) -> None:
        """Проверяет критически важные параметры."""
        if not self.tinkoff_token:
            raise ValueError("TINKOFF_TOKEN не задан в .env")
        if self.trading_mode not in ("PAPER", "LIVE"):
            raise ValueError(f"TRADING_MODE должен быть PAPER или LIVE, получено: {self.trading_mode}")
        if self.tariff not in TARIFF_COMMISSIONS:
            raise ValueError(f"TARIFF должен быть investor или trader, получено: {self.tariff}")
        if self.trading_mode == "LIVE" and not self.tinkoff_account_id:
            raise ValueError("TINKOFF_ACCOUNT_ID обязателен для LIVE режима")
        logger.info(
            "Config OK — mode=%s, tickers=%s, tariff=%s (%.2f%%)",
            self.trading_mode,
            ",".join(self.tickers),
            self.tariff,
            self.commission_rate * 100,
        )


# Singleton (mutable — GUI can change fields)
settings = Settings()
