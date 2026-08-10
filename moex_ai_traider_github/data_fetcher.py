"""
data_fetcher.py — Получение свечей через Tinkoff Invest API v2
и расчёт технических индикаторов через pandas_ta.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import pandas_ta as ta
from t_tech.invest import (
    CandleInterval,
    Client,
)
from t_tech.invest.utils import quotation_to_decimal

from config import settings

logger = logging.getLogger(__name__)


def _quotation_to_float(q) -> float:
    """Конвертирует Quotation / MoneyValue Tinkoff API → float."""
    return float(quotation_to_decimal(q))


class DataFetcher:
    """Загружает свечи из Tinkoff API и рассчитывает индикаторы."""

    def __init__(self, token: str | None = None):
        self.token = token or settings.tinkoff_token
        self._figi_cache: dict[str, str] = {}

    # ── Resolve ticker → FIGI ────────────────────────────────────────────
    def resolve_figi(self, ticker: str) -> str:
        """Находит FIGI по тикеру (кеширует). Ищем именно акции на MOEX."""
        if ticker in self._figi_cache:
            return self._figi_cache[ticker]

        with Client(self.token) as client:
            # Ищем сначала среди акций
            instruments = client.instruments.shares()
            for inst in instruments.instruments:
                if inst.ticker.upper() == ticker.upper() and ("moex" in inst.exchange.lower() or "moex_evening" in inst.exchange.lower()):
                    self._figi_cache[ticker] = inst.figi
                    logger.info("Resolved %s → FIGI %s (MOEX %s)", ticker, inst.figi, inst.name)
                    return inst.figi
            
            # Если не нашли в акциях, ищем везде (для индексов или ETF, если нужно)
            search = client.instruments.find_instrument(query=ticker)
            for inst in search.instruments:
                if inst.ticker.upper() == ticker.upper():
                    self._figi_cache[ticker] = inst.figi
                    logger.info("Resolved %s → FIGI %s (Common Search: %s)", ticker, inst.figi, inst.name)
                    return inst.figi

        raise ValueError(f"Тикер '{ticker}' не найден в Tinkoff API на MOEX")

    # ── Get candles ──────────────────────────────────────────────────────
    def get_candles(
        self,
        ticker: str,
        interval: CandleInterval = CandleInterval.CANDLE_INTERVAL_HOUR,
        count: int = 100,
    ) -> pd.DataFrame:
        figi = self.resolve_figi(ticker)
        now = datetime.now(timezone.utc)
        
        # Берем запас по времени (14 дней), чтобы гарантированно набрать 100 свечей
        from_dt = now - timedelta(days=14)

        with Client(self.token) as client:
            candles_response = client.market_data.get_candles(
                figi=figi,
                from_=from_dt,
                to=now,
                interval=interval,
            )
            all_candles = candles_response.candles

        if not all_candles:
            logger.warning("%s: Свечи не получено от API (FIGI: %s)", ticker, figi)
            return pd.DataFrame()

        logger.info("%s: Получено %d свечей из API", ticker, len(all_candles))

        rows = []
        for c in all_candles:
            rows.append({
                "datetime": c.time,
                "open": _quotation_to_float(c.open),
                "high": _quotation_to_float(c.high),
                "low": _quotation_to_float(c.low),
                "close": _quotation_to_float(c.close),
                "volume": c.volume,
            })


        df = pd.DataFrame(rows)
        df.set_index("datetime", inplace=True)
        df.sort_index(inplace=True)

        logger.info(
            "Loaded %d candles for %s [%s → %s]",
            len(df),
            ticker,
            df.index[0],
            df.index[-1],
        )
        return df

    # ── Compute indicators ───────────────────────────────────────────────
    @staticmethod
    def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Добавляет технические индикаторы к DataFrame свечей:
        - EMA_50, EMA_200  (тренд)
        - RSI_14           (осциллятор)
        - CDL_ENGULFING     (бычье/медвежье поглощение)
        - CDL_HAMMER        (молот)
        """
        if df.empty or len(df) < 50:
            logger.warning("Недостаточно данных для расчёта индикаторов (нужно ≥ 50)")
            return df

        # Trend — EMA
        df["EMA_50"] = ta.ema(df["close"], length=50)
        df["EMA_200"] = ta.ema(df["close"], length=200)

        # Oscillator — RSI
        df["RSI_14"] = ta.rsi(df["close"], length=14)

        # Candlestick patterns (pandas_ta cdl_pattern)
        # We calculate the core ones explicitly to ensure they exist.
        for pat in ["engulfing", "shootingstar", "doji", "morningstar", "eveningstar", "3whitesoldiers", "3blackcrows"]:
            try:
                res = ta.cdl_pattern(df["open"], df["high"], df["low"], df["close"], name=pat)
                if res is not None and not res.empty:
                    df[f"CDL_{pat.upper()}"] = res.iloc[:, 0]
                else:
                    df[f"CDL_{pat.upper()}"] = 0
            except Exception:
                df[f"CDL_{pat.upper()}"] = 0

        # CDL_HAMMER (Молот)
        try:
            # Ручное определение молота:
            # Нижняя тень ≥ 2× тело, верхняя тень минимальна
            body = abs(df["close"] - df["open"])
            lower_shadow = df[["open", "close"]].min(axis=1) - df["low"]
            upper_shadow = df["high"] - df[["open", "close"]].max(axis=1)
            total_range = df["high"] - df["low"]

            is_hammer = (
                (lower_shadow >= 2 * body)
                & (upper_shadow <= body * 0.5)
                & (total_range > 0)
            )
            df["CDL_HAMMER"] = is_hammer.astype(int) * 100
        except Exception:
            df["CDL_HAMMER"] = 0

        # Gaps
        try:
            df["GAP_UP"] = (df["low"] > df["high"].shift(1)).astype(int) * 100
            df["GAP_DOWN"] = (df["high"] < df["low"].shift(1)).astype(int) * -100
        except Exception:
            df["GAP_UP"] = 0
            df["GAP_DOWN"] = 0

        logger.info(
            "Indicators computed — last row: EMA50=%.2f, EMA200=%s, RSI=%.2f",
            df["EMA_50"].iloc[-1] if pd.notna(df["EMA_50"].iloc[-1]) else 0.0,
            f'{df["EMA_200"].iloc[-1]:.2f}' if pd.notna(df.get("EMA_200", pd.Series()).iloc[-1] if "EMA_200" in df else None) else "N/A",
            df["RSI_14"].iloc[-1] if pd.notna(df["RSI_14"].iloc[-1]) else 0.0,
        )

        return df

    @staticmethod
    def get_pivot_points(df: pd.DataFrame, window: int = 5) -> str:
        """Finds recent geometrical peaks (resistance) and troughs (support) for Chart Patterns."""
        if len(df) < window * 2: return "Недостаточно данных"
        
        pivots = []
        recent_df = df.tail(60) # Analyze last 60 candles
        closes = recent_df['close'].values
        dates = recent_df.index.strftime('%H:%M').values
        
        for i in range(window, len(closes) - window):
            # Check for local max (Resistance)
            is_max = True
            for j in range(1, window + 1):
                if closes[i] <= closes[i - j] or closes[i] <= closes[i + j]:
                    is_max = False
                    break
            if is_max:
                pivots.append(f"Пик({dates[i]}={closes[i]:.2f})")
                
            # Check for local min (Support)
            is_min = True
            for j in range(1, window + 1):
                if closes[i] >= closes[i - j] or closes[i] >= closes[i + j]:
                    is_min = False
                    break
            if is_min:
                pivots.append(f"Дно({dates[i]}={closes[i]:.2f})")
                
        # Add the very last close to anchor the current reality
        if len(closes) > 0:
            pivots.append(f"Сейчас({dates[-1]}={closes[-1]:.2f})")
        
        return " -> ".join(pivots[-12:]) if pivots else "Нет явных экстремумов"
