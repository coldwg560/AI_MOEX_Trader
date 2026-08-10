#!/usr/bin/env python3
"""
gui.py — MOEX AI Trader v3 — Desktop GUI (pywebview).

Тёмный, стильный интерфейс для управления торговым ботом.
Поддержка нескольких тикеров, отображение индикаторов,
история сделок, лог активности.
"""

import json
import sys
import logging
import webview
import dotenv

from config import settings, _env_path
from bot_engine import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("trading_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("gui")


# ═══════════════════════════════════════════════════════════════════════════
# Python ↔ JS Bridge
# ═══════════════════════════════════════════════════════════════════════════

class Api:
    """Exposed to JavaScript via pywebview."""

    def get_status(self) -> str:
        """Poll current bot state — called every 800ms from JS."""
        positions = []
        if engine.broker:
            for ticker in settings.tickers:
                pos = engine.broker.get_position(ticker)
                if pos:
                    pnl = 0.0
                    # Try to get latest close for this ticker
                    for r in reversed(engine.cycle_results):
                        if r.ticker == ticker and r.close > 0:
                            pnl = (r.close - pos.entry_price) * pos.quantity
                            break
                    positions.append({
                        "ticker": pos.ticker,
                        "qty": pos.quantity,
                        "entry": round(pos.entry_price, 2),
                        "tp": round(pos.take_profit, 2),
                        "sl": round(pos.stop_loss, 2),
                        "pnl": round(pnl, 2),
                        "opened": pos.opened_at,
                    })

        # Latest result per ticker
        latest = {}
        for r in engine.cycle_results:
            latest[r.ticker] = {
                "ticker": r.ticker,
                "close": round(r.close, 2) if r.close else 0,
                "ema50": round(r.ema50, 2) if r.ema50 else None,
                "ema200": round(r.ema200, 2) if r.ema200 else None,
                "rsi": round(r.rsi, 1) if r.rsi else None,
                "patterns_str": r.patterns_str if hasattr(r, 'patterns_str') else "",
                "filter": bool(r.filter_passed),
                "action": r.action_taken,
                "llm": r.llm_decision,
                "reason": r.llm_reason,
                "time": r.timestamp,
            }

        # Trade log from broker
        trades = []
        if engine.broker and hasattr(engine.broker, 'trade_log'):
            for t in reversed(engine.broker.trade_log[-30:]):
                trades.append(t)

        return json.dumps({
            "running": engine.is_running,
            "balance": round(engine.broker.get_balance(), 2) if engine.broker else settings.paper_balance,
            "mode": settings.trading_mode,
            "tickers": settings.tickers,
            "positions": positions,
            "latest": latest,
            "trades": trades,
            "logs": engine.logs[-100:],
            "log_count": engine.total_logs_emitted,
            "cycles": engine.cycles_completed,
            "lastCycle": engine.last_cycle_time,
            "commission": round(engine.broker.total_commission, 2) if engine.broker and hasattr(engine.broker, 'total_commission') else 0,
        })

    def start_bot(self) -> str:
        try:
            engine.start()
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    def stop_bot(self) -> str:
        engine.stop()
        return json.dumps({"ok": True})

    def force_cycle(self) -> str:
        engine.force_cycle()
        return json.dumps({"ok": True})

    def get_settings(self) -> str:
        return json.dumps({
            "tinkoff_token": settings.tinkoff_token[:8] + "..." if settings.tinkoff_token else "",
            "tickers": ",".join(settings.tickers),
            "llm_api_url": settings.llm_api_url,
            "llm_api_key": settings.llm_api_key[:8] + "..." if settings.llm_api_key else "",
            "llm_model": settings.llm_model,
            "tariff": settings.tariff,
            "paper_balance": settings.paper_balance,
            "mode": settings.trading_mode,
            "user_strategy": settings.user_strategy,
        })

    def save_settings(self, data_json: str) -> str:
        try:
            d = json.loads(data_json)
            if d.get("tickers"):
                settings.tickers = [t.strip() for t in d["tickers"].split(",") if t.strip()]
                dotenv.set_key(str(_env_path), "TICKERS", d["tickers"])
            if d.get("llm_model"):
                settings.llm_model = d["llm_model"].strip()
                dotenv.set_key(str(_env_path), "LLM_MODEL", settings.llm_model)
            if d.get("llm_api_key") and not d["llm_api_key"].endswith("..."):
                settings.llm_api_key = d["llm_api_key"].strip()
                dotenv.set_key(str(_env_path), "LLM_API_KEY", settings.llm_api_key)
            if d.get("llm_api_url"):
                settings.llm_api_url = d["llm_api_url"].strip()
                dotenv.set_key(str(_env_path), "LLM_API_URL", settings.llm_api_url)
            if d.get("tariff") in ("investor", "trader"):
                settings.tariff = d["tariff"]
                dotenv.set_key(str(_env_path), "TARIFF", settings.tariff)
            if d.get("mode") in ("PAPER", "LIVE"):
                settings.trading_mode = d["mode"]
                dotenv.set_key(str(_env_path), "TRADING_MODE", settings.trading_mode)
            if "user_strategy" in d:
                settings.user_strategy = d["user_strategy"].strip()
                dotenv.set_key(str(_env_path), "USER_STRATEGY", settings.user_strategy)
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    def check_brain(self) -> str:
        """Проверяет доступность OpenRouter/LLM API."""
        try:
            import requests
            url = f"{settings.llm_api_url.rstrip('/')}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.llm_api_key}"
            }
            payload = {
                "model": settings.llm_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code == 200:
                return json.dumps({"ok": True, "msg": "Доступ к мозгу установлен! ИИ отвечает."})
            else:
                return json.dumps({"ok": False, "msg": f"Ошибка {resp.status_code}: {resp.text[:100]}"})
        except Exception as e:
            return json.dumps({"ok": False, "msg": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
# HTML Template
# ═══════════════════════════════════════════════════════════════════════════

HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

  * { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0f0f13;
    --surface: #1a1a22;
    --surface2: #22222d;
    --surface3: #2a2a36;
    --border: #2f2f3a;
    --border-light: #3a3a48;
    --text: #e8e8f0;
    --text-dim: #9090a0;
    --text-dimmer: #606070;
    --green: #00d68f;
    --green-dim: #00d68f40;
    --red: #ff4d6a;
    --red-dim: #ff4d6a40;
    --blue: #4d8eff;
    --blue-dim: #4d8eff30;
    --yellow: #ffc554;
    --yellow-dim: #ffc55430;
    --purple: #b47aff;
    --accent: #4d8eff;
    --radius: 8px;
  }

  body {
    font-family: 'Inter', -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }

  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #3a3a48; border-radius: 10px; }
  ::-webkit-scrollbar-thumb:hover { background: #4a4a58; }

  /* ── HEADER ─────────────────────────────────── */
  .header {
    height: 46px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    flex-shrink: 0;
  }
  .header-left { display: flex; align-items: center; gap: 14px; }
  .logo {
    font-size: 15px; font-weight: 800;
    background: linear-gradient(135deg, var(--blue), var(--purple));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
  }
  .header-badge {
    font-size: 9px; font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .badge-paper { background: var(--blue-dim); color: var(--blue); }
  .badge-live { background: var(--red-dim); color: var(--red); }
  .header-right { display: flex; align-items: center; gap: 16px; }
  .status-pill {
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 600;
    padding: 4px 12px;
    border-radius: 20px;
  }
  .status-off { background: var(--surface3); color: var(--text-dim); }
  .status-on { background: var(--green-dim); color: var(--green); }
  .status-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: currentColor;
  }
  .status-on .status-dot {
    box-shadow: 0 0 8px var(--green);
    animation: glow 2s infinite;
  }
  @keyframes glow {
    0%,100% { opacity: 1; } 50% { opacity: .4; }
  }

  /* ── MAIN LAYOUT ────────────────────────────── */
  .main { display: flex; flex: 1; overflow: hidden; }

  /* ── LEFT SIDEBAR ───────────────────────────── */
  .sidebar {
    width: 280px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    overflow-y: auto;
  }
  .sidebar-section {
    padding: 16px;
    border-bottom: 1px solid var(--border);
  }
  .section-label {
    font-size: 10px; font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--text-dimmer);
    margin-bottom: 12px;
  }

  /* Balance card */
  .balance-card {
    background: linear-gradient(135deg, #1e1e2e, #2a2a3e);
    border: 1px solid var(--border-light);
    border-radius: var(--radius);
    padding: 14px;
  }
  .balance-label { font-size: 10px; color: var(--text-dim); font-weight: 500; }
  .balance-value {
    font-size: 26px; font-weight: 800; margin: 4px 0;
    background: linear-gradient(135deg, var(--green), #00e6a0);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .balance-row {
    display: flex; justify-content: space-between;
    font-size: 10px; color: var(--text-dim); margin-top: 6px;
  }

  /* Settings form */
  .form-label {
    font-size: 10px; color: var(--text-dim); font-weight: 500;
    margin-bottom: 4px; margin-left: 2px;
  }
  .form-input, .form-select {
    width: 100%;
    background: var(--surface3);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    padding: 8px 10px;
    font-size: 12px;
    font-family: inherit;
    margin-bottom: 10px;
    outline: none;
    transition: border-color .2s;
  }
  .form-input:focus { border-color: var(--accent); }
  .form-input::placeholder { color: var(--text-dimmer); }
  .btn {
    width: 100%;
    padding: 9px;
    border: none;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    transition: all .2s;
    margin-bottom: 6px;
  }
  .btn-save { background: var(--surface3); color: var(--text); border: 1px solid var(--border); }
  .btn-save:hover { background: var(--border-light); }

  /* Positions */
  .pos-card {
    background: var(--surface3);
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 6px;
    border-left: 3px solid var(--green);
    transition: transform .15s;
  }
  .pos-card:hover { transform: translateX(2px); }
  .pos-card.neg { border-left-color: var(--red); }
  .pos-top { display: flex; justify-content: space-between; align-items: center; }
  .pos-ticker { font-size: 13px; font-weight: 700; }
  .pos-pnl { font-size: 12px; font-weight: 700; }
  .pos-pnl.pos { color: var(--green); }
  .pos-pnl.neg { color: var(--red); }
  .pos-details { display: flex; gap: 12px; font-size: 9px; color: var(--text-dim); margin-top: 4px; }

  /* Start / Stop button */
  .btn-action {
    width: 100%;
    padding: 14px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 700;
    font-family: inherit;
    cursor: pointer;
    transition: all .25s;
    margin-top: auto;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }
  .btn-start {
    background: linear-gradient(135deg, #2563eb, #4d8eff);
    color: white;
    box-shadow: 0 4px 15px #2563eb50;
  }
  .btn-start:hover { box-shadow: 0 6px 20px #2563eb70; transform: translateY(-1px); }
  .btn-stop { background: var(--red); color: white; box-shadow: 0 4px 15px #ff4d6a40; }
  .btn-stop:hover { box-shadow: 0 6px 20px #ff4d6a60; }

  /* ── CENTER ─────────────────────────────────── */
  .center {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  /* Ticker cards row */
  .tickers-bar {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    overflow-x: auto;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .ticker-card {
    min-width: 160px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 10px 14px;
    flex-shrink: 0;
    transition: border-color .2s;
  }
  .ticker-card.active { border-color: var(--accent); }
  .ticker-card.signal-buy { border-color: var(--green); box-shadow: 0 0 12px var(--green-dim); }
  .ticker-card.signal-sell { border-color: var(--red); box-shadow: 0 0 12px var(--red-dim); }
  .tc-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
  .tc-name { font-size: 14px; font-weight: 700; }
  .tc-badge {
    font-size: 8px; font-weight: 700; padding: 2px 6px;
    border-radius: 4px; text-transform: uppercase;
  }
  .tc-badge-buy { background: var(--green-dim); color: var(--green); }
  .tc-badge-hold { background: var(--yellow-dim); color: var(--yellow); }
  .tc-badge-skip { background: var(--surface3); color: var(--text-dimmer); }
  .tc-badge-error { background: var(--red-dim); color: var(--red); }
  .tc-badge-tp { background: var(--green-dim); color: var(--green); }
  .tc-badge-sl { background: var(--red-dim); color: var(--red); }
  .tc-price { font-size: 18px; font-weight: 700; margin: 2px 0; }
  .tc-indicators { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
  .tc-ind {
    font-size: 9px; font-weight: 500; padding: 2px 6px;
    background: var(--surface3); border-radius: 4px; color: var(--text-dim);
  }
  .tc-ind.pass { color: var(--green); background: var(--green-dim); }
  .tc-ind.fail { color: var(--red); background: var(--red-dim); }

  /* Log area */
  .log-header {
    height: 36px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    flex-shrink: 0;
  }
  .log-area {
    flex: 1;
    padding: 12px 16px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    line-height: 1.8;
    color: var(--text-dim);
    background: var(--bg);
  }
  .log-line { padding: 1px 0; }
  .l-green { color: var(--green); }
  .l-red { color: var(--red); }
  .l-blue { color: var(--blue); }
  .l-yellow { color: var(--yellow); }
  .l-purple { color: var(--purple); }
  .l-dim { color: var(--text-dimmer); }

  /* ── RIGHT PANEL ────────────────────────────── */
  .right-panel {
    width: 270px;
    background: var(--surface);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }
  .right-header {
    height: 36px;
    display: flex;
    align-items: center;
    padding: 0 16px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .trades-list { flex: 1; overflow-y: auto; }
  .trade-item {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    transition: background .15s;
  }
  .trade-item:hover { background: var(--surface2); }
  .trade-top { display: flex; justify-content: space-between; font-size: 10px; color: var(--text-dim); }
  .trade-action { font-weight: 700; }
  .trade-action.buy { color: var(--green); }
  .trade-action.sell { color: var(--red); }
  .trade-mid { display: flex; justify-content: space-between; margin-top: 4px; align-items: baseline; }
  .trade-ticker { font-size: 14px; font-weight: 700; }
  .trade-amount { font-size: 12px; font-weight: 500; }
  .trade-pnl { font-size: 10px; margin-top: 3px; }
  .trade-pnl.pos { color: var(--green); }
  .trade-pnl.neg { color: var(--red); }
  .trade-reason { font-size: 9px; color: var(--text-dimmer); margin-top: 4px; line-height: 1.4; }

  .empty-state {
    text-align: center; color: var(--text-dimmer);
    padding: 40px 20px; font-size: 12px;
  }

  /* ── FOOTER ─────────────────────────────────── */
  .footer {
    height: 24px;
    background: var(--surface);
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    font-size: 9px;
    color: var(--text-dimmer);
    flex-shrink: 0;
  }
  .footer-left { display: flex; gap: 16px; }
  .f-green { color: var(--green); }
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div class="header-left">
    <span class="logo">MOEX AI Trader</span>
    <span class="header-badge badge-paper" id="modeBadge">PAPER</span>
  </div>
  <div class="header-right">
    <div class="status-pill status-off" id="statusPill">
      <div class="status-dot"></div>
      <span id="statusText">Остановлен</span>
    </div>
  </div>
</div>

<!-- MAIN -->
<div class="main">

  <!-- LEFT SIDEBAR -->
  <div class="sidebar">
    <!-- Balance -->
    <div class="sidebar-section">
      <div class="section-label">💰 Портфель</div>
      <div class="balance-card">
        <div class="balance-label">Доступно</div>
        <div class="balance-value" id="balanceValue">100 000 ₽</div>
        <div class="balance-row">
          <span>Комиссии: <span id="totalComm">0</span> ₽</span>
          <span>Циклов: <span id="cycleCount">0</span></span>
        </div>
      </div>
    </div>

    <!-- Positions -->
    <div class="sidebar-section" style="flex:1;overflow-y:auto;">
      <div class="section-label">📦 Открытые позиции</div>
      <div id="positionsList">
        <div class="empty-state">Нет позиций</div>
      </div>
    </div>

    <!-- Settings -->
    <div class="sidebar-section">
      <div class="section-label">⚙ Настройки</div>

      <div class="form-label">Стратегия ИИ</div>
      <textarea class="form-input" id="inStrategy" placeholder="Напишите свою стратегию..." rows="4"></textarea>

      <div class="form-label">Тикеры (через запятую)</div>
      <input class="form-input" id="inTickers" placeholder="SBER,GAZP,LKOH" />

      <div class="form-label">Модель LLM (OpenRouter)</div>
      <input class="form-input" id="inModel" placeholder="deepseek/deepseek-v3.2" />

      <div class="form-label">Режим торговли</div>
      <select class="form-select" id="inMode">
        <option value="PAPER">PAPER (Симуляция)</option>
        <option value="LIVE">LIVE (Реальные деньги)</option>
      </select>

      <div class="form-label">Тариф</div>
      <select class="form-select" id="inTariff">
        <option value="investor">Инвестор (0.3%)</option>
        <option value="trader">Трейдер (0.05%)</option>
      </select>

      <button class="btn btn-save" onclick="saveSettings()">💾 Сохранить</button>
      <button class="btn btn-save" style="margin-top: 10px; background: var(--purple); color: white;" onclick="checkBrain(event)">🧠 Проверить доступ к ИИ</button>
    </div>

    <!-- Start/Stop -->
    <div class="sidebar-section" style="border-bottom:none;padding-top:8px;">
      <button class="btn-action btn-start" id="actionBtn" onclick="toggleBot()">
        ▶ Запустить бота
      </button>
      <button class="btn btn-save" style="margin-top: 10px;" onclick="refreshData()">
        🔄 Обновить
      </button>
    </div>
  </div>

  <!-- CENTER -->
  <div class="center">
    <!-- Ticker cards -->
    <div class="tickers-bar" id="tickersBar"></div>

    <!-- Log -->
    <div class="log-header">
      <span class="section-label" style="margin:0">📋 Лог активности</span>
      <span style="font-size:10px;color:var(--text-dimmer)" id="lastCycleTime">—</span>
    </div>
    <div class="log-area" id="logArea"></div>
  </div>

  <!-- RIGHT PANEL -->
  <div class="right-panel">
    <div class="right-header">
      <span class="section-label" style="margin:0">📊 Сделки</span>
    </div>
    <div class="trades-list" id="tradesList">
      <div class="empty-state">Пока сделок нет.<br>Запустите бота.</div>
    </div>
  </div>

</div>

<!-- FOOTER -->
<div class="footer">
  <div class="footer-left">
    <span>Тариф: <span id="footerTariff" class="f-green">investor</span></span>
  </div>
  <span>MOEX AI Trader v3</span>
</div>

<script>
let isRunning = false;
let lastLogCount = 0;

async function loadSettings() {
  try {
    const raw = await pywebview.api.get_settings();
    const s = JSON.parse(raw);
    document.getElementById('inStrategy').value = s.user_strategy || '';
    document.getElementById('inTickers').value = s.tickers || '';
    document.getElementById('inModel').value = s.llm_model || '';
    document.getElementById('inMode').value = s.mode || 'PAPER';
    document.getElementById('inTariff').value = s.tariff || 'investor';
    document.getElementById('footerTariff').textContent = s.tariff;
    const badge = document.getElementById('modeBadge');
    badge.textContent = s.mode;
    badge.className = 'header-badge ' + (s.mode === 'LIVE' ? 'badge-live' : 'badge-paper');
  } catch(e) {}
}

async function saveSettings() {
  const data = {
    user_strategy: document.getElementById('inStrategy').value,
    tickers: document.getElementById('inTickers').value,
    llm_model: document.getElementById('inModel').value,
    mode: document.getElementById('inMode').value,
    tariff: document.getElementById('inTariff').value,
  };
  await pywebview.api.save_settings(JSON.stringify(data));
  await loadSettings();
}

async function refreshData() {
  await pywebview.api.force_cycle();
}

async function toggleBot() {
  if (!isRunning) {
    await saveSettings();
    const r = JSON.parse(await pywebview.api.start_bot());
    if (!r.ok) alert('Ошибка: ' + r.error);
  } else {
    await pywebview.api.stop_bot();
  }
}

async function checkBrain(e) {
  const btn = e.target;
  const oldHtml = btn.innerHTML;
  btn.innerHTML = '⏳ Проверка...';
  try {
    const raw = await pywebview.api.check_brain();
    const res = JSON.parse(raw);
    if (res.ok) {
      alert('✅ Успешно: ' + res.msg);
    } else {
      alert('❌ Ошибка: ' + res.msg);
    }
  } catch(err) {
    alert('❌ Системная ошибка: ' + err);
  } finally {
    btn.innerHTML = oldHtml;
  }
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function colorLog(line) {
  const e = esc(line);
  if (line.includes('❌') || line.includes('ERROR')) return `<span class="l-red">${e}</span>`;
  if (line.includes('🟢') || line.includes('✅') || line.includes('BUY')) return `<span class="l-green">${e}</span>`;
  if (line.includes('🔴') || line.includes('SELL') || line.includes('🛑')) return `<span class="l-red">${e}</span>`;
  if (line.includes('🟡') || line.includes('HOLD')) return `<span class="l-yellow">${e}</span>`;
  if (line.includes('📊') || line.includes('📈') || line.includes('📦')) return `<span class="l-blue">${e}</span>`;
  if (line.includes('💡') || line.includes('🤖')) return `<span class="l-purple">${e}</span>`;
  if (line.includes('⏳') || line.includes('===')) return `<span class="l-dim">${e}</span>`;
  return `<span>${e}</span>`;
}

function actionBadge(action) {
  if (!action) return '';
  const map = {
    'BUY': 'tc-badge-buy', 'HOLD': 'tc-badge-hold',
    'SKIP': 'tc-badge-skip', 'ERROR': 'tc-badge-error',
    'SELL_TP': 'tc-badge-tp', 'SELL_SL': 'tc-badge-sl',
    'HOLD_POSITION': 'tc-badge-hold', 'BUY_FAILED': 'tc-badge-error',
  };
  const cls = map[action] || 'tc-badge-skip';
  const label = action.replace('_', ' ');
  return `<span class="tc-badge ${cls}">${label}</span>`;
}

async function poll() {
  try {
    const raw = await pywebview.api.get_status();
    const d = JSON.parse(raw);
    isRunning = d.running;

    // Status
    const pill = document.getElementById('statusPill');
    const stxt = document.getElementById('statusText');
    const btn = document.getElementById('actionBtn');

    if (d.running) {
      pill.className = 'status-pill status-on';
      stxt.textContent = 'Работает';
      btn.className = 'btn-action btn-stop';
      btn.innerHTML = '⏹ Остановить';
    } else {
      pill.className = 'status-pill status-off';
      stxt.textContent = 'Остановлен';
      btn.className = 'btn-action btn-start';
      btn.innerHTML = '▶ Запустить бота';
    }

    // Balance
    document.getElementById('balanceValue').textContent =
      d.balance.toLocaleString('ru-RU', {minimumFractionDigits: 2}) + ' ₽';
    document.getElementById('totalComm').textContent =
      d.commission.toLocaleString('ru-RU', {minimumFractionDigits: 2});
    document.getElementById('cycleCount').textContent = d.cycles;
    document.getElementById('lastCycleTime').textContent =
      d.lastCycle !== '—' ? 'Последний цикл: ' + d.lastCycle : '—';

    // Ticker cards
    const bar = document.getElementById('tickersBar');
    let cardsHtml = '';
    for (const ticker of d.tickers) {
      const info = d.latest[ticker];
      let cardClass = 'ticker-card';
      if (info) {
        if (info.action === 'BUY') cardClass += ' signal-buy';
        else if (info.action && info.action.startsWith('SELL')) cardClass += ' signal-sell';
      }
      cardsHtml += `<div class="${cardClass}">`;
      cardsHtml += `<div class="tc-top"><span class="tc-name">${ticker}</span>`;
      cardsHtml += info ? actionBadge(info.action) : '<span class="tc-badge tc-badge-skip">—</span>';
      cardsHtml += '</div>';
      if (info && info.close > 0) {
        cardsHtml += `<div class="tc-price">${info.close.toFixed(2)} ₽</div>`;
        cardsHtml += '<div class="tc-indicators">';
        if (info.ema50 != null) cardsHtml += `<span class="tc-ind">EMA50: ${info.ema50.toFixed(1)}</span>`;
        if (info.ema200 != null) {
          const pass = info.close > info.ema200;
          cardsHtml += `<span class="tc-ind ${pass ? 'pass' : 'fail'}">EMA200: ${info.ema200.toFixed(1)}</span>`;
        }
        if (info.rsi != null) {
          const pass = info.rsi < 50;
          cardsHtml += `<span class="tc-ind ${pass ? 'pass' : 'fail'}">RSI: ${info.rsi.toFixed(1)}</span>`;
        }
        if (info.patterns_str) {
          const items = info.patterns_str.match(/\\[([^]+)\\]([^\\[]+)\\[\\/\\]/g);
          if (items) {
            items.forEach(item => {
              const m = item.match(/\\[(.*)\\]([^\\[]+)\\[\\/\\]/);
              if (m) {
                cardsHtml += `<span class="tc-ind ${m[1] === 'green' ? 'pass' : 'fail'}">${m[2]}</span>`;
              }
            });
          }
        }
        cardsHtml += '</div>';
      } else {
        cardsHtml += '<div class="tc-price" style="color:var(--text-dimmer)">—</div>';
      }
      cardsHtml += '</div>';
    }
    bar.innerHTML = cardsHtml;

    // Positions
    const posEl = document.getElementById('positionsList');
    if (d.positions.length === 0) {
      posEl.innerHTML = '<div class="empty-state">Нет позиций</div>';
    } else {
      posEl.innerHTML = d.positions.map(p => {
        const cls = p.pnl >= 0 ? '' : 'neg';
        const pnlCls = p.pnl >= 0 ? 'pos' : 'neg';
        const sign = p.pnl > 0 ? '+' : '';
        return `<div class="pos-card ${cls}">
          <div class="pos-top">
            <span class="pos-ticker">${p.ticker} ×${p.qty}</span>
            <span class="pos-pnl ${pnlCls}">${sign}${p.pnl.toFixed(2)} ₽</span>
          </div>
          <div class="pos-details">
            <span>Вход: ${p.entry.toFixed(2)}</span>
            <span>TP: ${p.tp.toFixed(2)}</span>
            <span>SL: ${p.sl.toFixed(2)}</span>
          </div>
        </div>`;
      }).join('');
    }

    // Logs
    if (d.log_count !== lastLogCount) {
      const logEl = document.getElementById('logArea');
      let newCount = d.log_count - lastLogCount;
      if (lastLogCount === 0 || newCount > d.logs.length) {
        logEl.innerHTML = d.logs.map(line => '<div class="log-line">' + colorLog(line) + '</div>').join('');
      } else {
        const newLogs = d.logs.slice(d.logs.length - newCount);
        let newHtml = '';
        for (const line of newLogs) {
          newHtml += '<div class="log-line">' + colorLog(line) + '</div>';
        }
        logEl.insertAdjacentHTML('beforeend', newHtml);
      }
      logEl.scrollTop = logEl.scrollHeight;
      lastLogCount = d.log_count;
    }

    // Trades
    if (d.trades.length > 0) {
      const tEl = document.getElementById('tradesList');
      tEl.innerHTML = d.trades.map(t => {
        const isBuy = t.action === 'BUY';
        const actCls = isBuy ? 'buy' : 'sell';
        const amount = (t.price * t.quantity).toLocaleString('ru-RU', {maximumFractionDigits: 0});
        let pnlHtml = '';
        if (t.pnl !== undefined && t.pnl !== 0) {
          const pcls = t.pnl >= 0 ? 'pos' : 'neg';
          const s = t.pnl > 0 ? '+' : '';
          pnlHtml = `<div class="trade-pnl ${pcls}">${s}${t.pnl.toFixed(2)} ₽</div>`;
        }
        let reasonHtml = '';
        if (t.reason) {
          reasonHtml = `<div class="trade-reason">${esc(t.reason)}</div>`;
        }
        return `<div class="trade-item">
          <div class="trade-top">
            <span>${t.time}</span>
            <span class="trade-action ${actCls}">${t.action}</span>
          </div>
          <div class="trade-mid">
            <span class="trade-ticker">${t.ticker} ×${t.quantity}</span>
            <span class="trade-amount">${amount} ₽</span>
          </div>
          ${pnlHtml}
          ${reasonHtml}
        </div>`;
      }).join('');
    }

  } catch(e) {}
}

window.addEventListener('pywebviewready', () => {
  loadSettings();
  setInterval(poll, 800);
});
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    api = Api()
    window = webview.create_window(
        "MOEX AI Trader v3",
        html=HTML,
        js_api=api,
        width=1200,
        height=750,
        min_size=(1000, 600),
        background_color="#0f0f13",
        frameless=False,
        easy_drag=False,
    )
    webview.start(gui="qt", debug=False)
