"""
strategy.py — Стратегия Smart Pullback (Long Only) + LLM Brain.

Фильтр:
  1. Цена > EMA 200 (восходящий тренд)
  2. RSI < 50 (откат / перепроданность)

Если фильтр пройден — формируем промпт и отправляем в LLM.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests

from data_fetcher import DataFetcher
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMDecision:
    """Результат решения LLM."""
    action: str        # "BUY" или "HOLD"
    quantity: int      # количество лотов (определяется LLM)
    take_profit: float  # абсолютная цена TP
    stop_loss: float    # абсолютная цена SL
    reason: str         # обоснование


class SmartPullbackStrategy:
    """
    Long-only стратегия с двухступенчатым фильтром и LLM-мозгом.

    Шаг 1 — Технический фильтр (check_filter):
        close > EMA200  AND  RSI < 50

    Шаг 2 — Запрос к LLM (ask_llm):
        Формируем промпт с данными индикаторов →
        получаем JSON {"action", "take_profit", "stop_loss", "reason"}.
    """

    # ── Фильтр ───────────────────────────────────────────────────────────
    @staticmethod
    def check_filter(df: pd.DataFrame) -> bool:
        """
        Пропускаем технический фильтр, чтобы решение полностью зависело от ИИ стратегии пользователя.
        """
        return True

    # ── Промпт ───────────────────────────────────────────────────────────
    @staticmethod
    def build_prompt(ticker: str, df: pd.DataFrame, balance: float, history: list = None) -> str:
        """Формирует текстовый промпт для LLM, объединяя индикаторы, паттерны свечей и экстремумы (волны)."""
        if history is None:
            history = []
        last = df.iloc[-1]

        close = last["close"]
        ema50 = last.get("EMA_50", "N/A")
        ema200 = last.get("EMA_200", "N/A")
        rsi = last.get("RSI_14", "N/A")

        # Собираем активные свечные паттерны (где значение != 0)
        active_cdl = []
        for col in df.columns:
            if col.startswith("CDL_") or col.startswith("GAP_"):
                val = last.get(col, 0)
                if val != 0:
                    name = col.replace("CDL_", "").replace("GAP_", "Гэп_")
                    direction = "Бычий" if val > 0 else "Медвежий"
                    active_cdl.append(f"{name}({direction})")

        cdl_str = ", ".join(active_cdl) if active_cdl else "Свечных паттернов не найдено"

        # Получаем экстремумы (восходящие/нисходящие тенденции, зоны П/С)
        pivots_str = DataFetcher.get_pivot_points(df, window=5)

        history_str = "Нет недавних сделок"
        if history:
            last_deals = [f"{h['time']} - {h['action']} по причине: {h['reason']} (цена {h.get('price', 'N/A')})" for h in history[-3:]]
            history_str = " | ".join(last_deals)

        prompt = (
            f"Ты — эксперт по алгоритмическому графическому анализу и трейдингу на Московской бирже.\n"
            f"Анализируй график и прими решение: покупать (BUY) или ждать (HOLD).\n"
            f"Шорт запрещён. Только лонг.\n\n"
            f"Бюджет: {balance:.2f} RUB\n"
            f"Тикер: {ticker}\n"
            f"Цена: {close:.2f}\n"
            f"Тренд: EMA50={ema50:.2f}, EMA200={ema200:.2f}\n"
            f"RSI(14): {rsi:.2f}\n"
            f"СВЕЧНЫЕ ПАТТЕРНЫ (на последней свече): {cdl_str}\n"
            f"ЭКСТРЕМУМЫ ГРАФИКА (Пики/Дно для геом. фигур): {pivots_str}\n"
            f"ИСТОРИЯ ПОСЛЕДНИХ СДЕЛОК (учитывай при входе): {history_str}\n\n"
            f"ИНСТРУКЦИЯ ПО ПАТТЕРНАМ (ТВОЯ СТРАТЕГИЯ):\n"
            f"{settings.user_strategy}\n\n"
            f"Ответь строго в JSON:\n"
            f'{{"action": "BUY" | "HOLD", "take_profit": float, "stop_loss": float, "quantity": int, "reason": "Опиши кратко в ОДНУ СТРОКУ (без переносов): 1) Тренд. 2) Найденные фигуры. 3) Причина действия."}}'
        )
        return prompt

    # ── LLM ──────────────────────────────────────────────────────────────
    @staticmethod
    def ask_llm(prompt: str) -> LLMDecision:
        """
        Отправляет промпт в OpenAI-совместимый API и парсит JSON ответ.

        Использует настройки из config: LLM_API_URL, LLM_API_KEY, LLM_MODEL.
        """
        url = f"{settings.llm_api_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}",
        }
        payload = {
            "model": settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты — торговый ИИ-ассистент. Отвечай ТОЛЬКО валидным JSON "
                        'в формате: {"action": "BUY"|"HOLD", "take_profit": float, '
                        '"stop_loss": float, "quantity": int, "reason": "string"}. '
                        "Никакого текста вне JSON. Важно: поле 'reason' должно быть написано строго в одну строку без символов переноса."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 300,
        }

        try:
            logger.info("Запрос к LLM (%s)...", settings.llm_model)
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # Пытаемся извлечь JSON более надежно
            content = content.replace("```json", "").replace("```", "").strip()
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                content = content[start:end+1]
            
            # Заменяем физические переносы строк внутри JSON на пробелы, 
            # чтобы избежать ошибки "Unterminated string" если ИИ перенес строку в reason
            content = content.replace("\n", " ").replace("\r", " ")

            decision = json.loads(content)

            result = LLMDecision(
                action=decision.get("action", "HOLD").upper(),
                quantity=int(decision.get("quantity", 0)),
                take_profit=float(decision.get("take_profit", 0)),
                stop_loss=float(decision.get("stop_loss", 0)),
                reason=decision.get("reason", "Нет обоснования"),
            )

            logger.info(
                "LLM решение: %s | TP=%.2f | SL=%.2f | %s",
                result.action, result.take_profit, result.stop_loss, result.reason,
            )
            return result

        except requests.RequestException as e:
            logger.error("Ошибка HTTP при запросе к LLM: %s", e)
            return LLMDecision(action="HOLD", quantity=0, take_profit=0, stop_loss=0, reason=f"HTTP error: {e}")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("Ошибка парсинга ответа LLM: %s", e)
            return LLMDecision(action="HOLD", quantity=0, take_profit=0, stop_loss=0, reason=f"Parse error: {e}")

    # ── Оркестратор ──────────────────────────────────────────────────────
    def evaluate(self, ticker: str, df: pd.DataFrame, balance: float, history: list = None) -> Optional[LLMDecision]:
        """
        Полный цикл оценки:
        1. Проверяет фильтр
        2. Если пройден — формирует промпт → спрашивает LLM
        3. Возвращает LLMDecision или None (если фильтр не пройден)
        """
        if not self.check_filter(df):
            logger.info("⏸  Фильтр не пройден — пропуск цикла.")
            return None

        logger.info("✅ Фильтр пройден — запрашиваем LLM...")
        prompt = self.build_prompt(ticker, df, balance, history)
        decision = self.ask_llm(prompt)

        return decision

    # ── Мониторинг портфеля ──────────────────────────────────────────────
    @staticmethod
    def build_monitoring_prompt(ticker: str, df: pd.DataFrame, entry_price: float, current_price: float, pnl_percent: float, tp: float, sl: float) -> str:
        last = df.iloc[-1]
        rsi = last.get("RSI_14", "N/A")
        ema50 = last.get("EMA_50", "N/A")
        ema200 = last.get("EMA_200", "N/A")
        
        rsi_str = f"{rsi:.2f}" if isinstance(rsi, (int, float)) else rsi
        ema50_str = f"{ema50:.2f}" if isinstance(ema50, (int, float)) else ema50
        ema200_str = f"{ema200:.2f}" if isinstance(ema200, (int, float)) else ema200

        prompt = (
            f"АКЦИЯ В ПОРТФЕЛЕ: {ticker}.\n"
            f"Цена входа: {entry_price:.2f}. Текущая цена: {current_price:.2f} ({pnl_percent:.2f}%).\n"
            f"Техданные: RSI={rsi_str}, EMA50={ema50_str}, EMA200={ema200_str}.\n"
            f"Текущие ордера: TakeProfit={tp:.2f}, StopLoss={sl:.2f}.\n\n"
            f"Твоя задача: Проанализировать, не изменился ли тренд. Выбери одно действие:\n"
            f"- 'HOLD': Продолжать держать до тейка.\n"
            f"- 'SELL_NOW': Закрыть позицию немедленно (например, если тренд сломался или RSI стал > 75).\n"
            f"- 'MOVE_STOP': Переставить StopLoss в точку безубытка (Entry Price), если профит уже > 2%, чтобы защитить сделку.\n"
            f"Верни строго JSON: {{\"action\": \"...\", \"reason\": \"...\"}}"
        )
        return prompt

    @staticmethod
    def ask_monitoring_llm(prompt: str) -> dict:
        url = f"{settings.llm_api_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}",
        }
        payload = {
            "model": settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты — торговый ИИ-ассистент, управляющий открытыми позициями. Отвечай ТОЛЬКО валидным JSON "
                        'в формате: {"action": "HOLD"|"SELL_NOW"|"MOVE_STOP", "reason": "string"}. '
                        "Никакого текста вне JSON. Поле 'reason' строго в одну строку."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 300,
        }

        try:
            logger.info("Запрос к LLM для мониторинга (%s)...", settings.llm_model)
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            content = content.replace("```json", "").replace("```", "").strip()
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                content = content[start:end+1]
                
            content = content.replace("\n", " ").replace("\r", " ")

            decision = json.loads(content)
            
            return {
                "action": decision.get("action", "HOLD").upper(),
                "reason": decision.get("reason", "Нет обоснования"),
            }
        except Exception as e:
            logger.error("Ошибка при запросе мониторинга к LLM: %s", e)
            return {"action": "HOLD", "reason": f"Error: {e}"}

