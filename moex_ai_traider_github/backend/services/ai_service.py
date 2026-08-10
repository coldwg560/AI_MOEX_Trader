import json
from openai import AsyncOpenAI
from models import TradeAction, AIRecommendation
from core.knowledge_base import get_knowledge_base

class OpenRouterTrader:
    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini"):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model

    async def analyze_market(
        self,
        ticker: str,
        price: float,
        portfolio_balance: float,
        recent_candles: list,
        indicators: dict,
        timeframe: str,
        positions_info: str
    ) -> AIRecommendation:

        knowledge = get_knowledge_base()

        prompt = f"""
{knowledge}

---

# CURRENT MARKET ANALYSIS TASK

You are analyzing the asset **{ticker}** on the Moscow Exchange (MOEX).
Timeframe: **{timeframe}**
Current Price: **{price:.2f} RUB**
Portfolio Cash Balance: **{portfolio_balance:.2f} RUB**

Current Positions:
{positions_info if positions_info else "None"}

## Computed Technical Indicators (real values):
{json.dumps(indicators, indent=2)}

## Recent Candles (OHLCV):
{json.dumps(recent_candles[-10:], indent=2)}

---

## YOUR TASK:
1. Analyze the above indicators against the knowledge base patterns and strategies.
2. Decide: BUY, SELL, or HOLD.
3. Your confidence must reflect how many indicators agree.
4. List which indicators and patterns you used.

Respond ONLY in valid JSON:
{{
  "action": "buy" | "sell" | "hold",
  "confidence": <integer 0-100>,
  "reasoning": "<2-3 sentences explaining your decision referencing specific indicators>",
  "indicators_used": "<comma separated list of indicators/patterns you checked>",
  "target_ticker": "{ticker}"
}}
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert algorithmic trading AI. You use technical analysis indicators, candlestick patterns, and proven strategies to make trading decisions. Always reference specific indicator values in your reasoning."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content
            data = json.loads(content)

            return AIRecommendation(
                action=TradeAction(data.get("action", "hold").lower()),
                confidence=int(data.get("confidence", 0)),
                reasoning=data.get("reasoning", "No reasoning provided."),
                target_ticker=ticker,
                indicators_used=data.get("indicators_used", "")
            )
        except Exception as e:
            return AIRecommendation(
                action=TradeAction.HOLD,
                confidence=0,
                reasoning=f"Error: {str(e)}",
                target_ticker=ticker,
                indicators_used=""
            )
