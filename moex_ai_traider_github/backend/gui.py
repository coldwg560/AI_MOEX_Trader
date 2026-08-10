"""
MOEX AI Trader — Native Desktop GUI via pywebview.

Uses pywebview to render the HTML/CSS design in a native window.
No browser. No localhost. Just a native desktop app with gorgeous UI.
"""
import os
import sys
import json
import asyncio
import threading
import webview

from config import config_manager
from core.bot import bot
from models import Timeframe

# ─────────────────────────────────────────────
#  Python ↔ JS Bridge (exposed to JavaScript)
# ─────────────────────────────────────────────
class Api:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def get_status(self):
        """Called by JS to poll current state."""
        portfolio = bot.market_service.get_portfolio()
        positions = []
        for p in portfolio["positions"]:
            pct = ((p.current_price - p.average_price) / p.average_price * 100) if p.average_price else 0
            positions.append({
                "name": p.name, "qty": p.quantity,
                "price": round(p.current_price, 2),
                "pnl": round(p.unrealized_pnl, 2),
                "pct": round(pct, 1)
            })

        trades = []
        for t in reversed(bot.trade_history[-30:]):
            trades.append({
                "time": t.timestamp, "action": t.action,
                "ticker": t.ticker.split(".")[0], "qty": t.quantity,
                "price": round(t.price, 2),
                "total": round(t.price * t.quantity, 2) if t.quantity else 0,
                "confidence": t.confidence, "reasoning": t.reasoning,
                "indicators": t.indicators, "pnl": round(t.pnl, 2)
            })

        return json.dumps({
            "running": bot.is_running,
            "balance": round(portfolio["balance_rub"], 2),
            "positions": positions,
            "trades": trades,
            "logs": bot.logs[-80:]
        })

    def save_settings(self, token, model_id, timeframe):
        s = config_manager.settings
        s.openrouter_token = token.strip()
        if model_id.strip():
            s.model_name = model_id.strip()
        tf_map = {"3h": Timeframe.H3, "6h": Timeframe.H6, "1d": Timeframe.D1}
        s.timeframe = tf_map.get(timeframe, Timeframe.H3)
        config_manager.save_settings(s)
        return "ok"

    def get_settings(self):
        s = config_manager.settings
        return json.dumps({
            "token": s.openrouter_token,
            "model": s.model_name,
            "timeframe": s.timeframe.value
        })

    def start_bot(self):
        if not bot.is_running:
            asyncio.run_coroutine_threadsafe(self._start(), self.loop)
        return "ok"

    def check_brain(self):
        s = config_manager.settings
        try:
            import requests
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {s.openrouter_token}"
            }
            payload = {
                "model": s.model_name,
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

    def stop_bot(self):
        bot.stop()
        return "ok"

    async def _start(self):
        bot.start()


# ─────────────────────────────────────────────
#  HTML Template
# ─────────────────────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

  * { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #1e1e1e;
    --win: #2d2d2d;
    --sidebar: #252525;
    --center: #1a1a1a;
    --titlebar: #3c3c3c;
    --footer: #333;
    --border: #3f3f3f;
    --input-bg: #333;
    --input-bd: #444;
    --text: #e0e0e0;
    --dim: #999;
    --dimmer: #777;
    --green: #27c93f;
    --green-light: #4ade80;
    --red: #dc2626;
    --red-light: #f87171;
    --blue: #60a5fa;
    --yellow: #facc15;
    --btn: #444;
    --btn-hover: #555;
  }

  body {
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    user-select: none;
  }

  /* SCROLLBAR */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: var(--sidebar); }
  ::-webkit-scrollbar-thumb { background: #4b4b4b; border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: #5a5a5a; }

  /* TITLE BAR */
  .titlebar {
    height: 38px; background: var(--titlebar);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 16px; border-bottom: 1px solid #252525; flex-shrink: 0;
  }
  .titlebar-left { display: flex; align-items: center; gap: 20px; }
  .dots { display: flex; gap: 6px; }
  .dot { width: 12px; height: 12px; border-radius: 50%; }
  .dot-r { background: #ff5f56; border: 1px solid #e0443e; }
  .dot-y { background: #ffbd2e; border: 1px solid #dea123; }
  .dot-g { background: #27c93f; border: 1px solid #1aab29; }
  .titlebar-title { font-size: 13px; font-weight: 600; color: #d1d1d1; }
  .status-ind { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--dim); }
  .status-dot.on { background: var(--green); box-shadow: 0 0 8px var(--green); }

  /* MAIN */
  .main { display: flex; flex: 1; overflow: hidden; }

  /* LEFT */
  .left {
    width: 280px; background: var(--sidebar);
    border-right: 1px solid var(--border);
    display: flex; flex-direction: column; padding: 14px; flex-shrink: 0;
    overflow-y: auto;
  }
  .section-title {
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1px; color: var(--dim); margin-bottom: 12px;
  }
  .form-label {
    font-size: 10px; color: #aaa; font-weight: 500; margin-bottom: 3px; margin-left: 2px;
  }
  .form-input, .form-select {
    width: 100%; background: var(--input-bg); border: 1px solid var(--input-bd);
    border-radius: 4px; color: #ccc; padding: 7px 10px; font-size: 12px;
    font-family: inherit; margin-bottom: 10px; outline: none;
    transition: border-color .2s;
  }
  .form-input:focus, .form-select:focus { border-color: var(--blue); }
  .form-input::placeholder { color: #666; }
  .btn-save {
    width: 100%; padding: 8px; background: var(--btn); border: 1px solid var(--btn-hover);
    color: white; border-radius: 4px; font-size: 12px; font-weight: 500;
    cursor: pointer; transition: background .2s; margin-bottom: 4px;
  }
  .btn-save:hover { background: var(--btn-hover); }
  .sep { height: 1px; background: var(--border); margin: 14px 0; }
  .balance-value { font-size: 22px; font-weight: 700; color: var(--green-light); margin: 4px 0 12px; }

  /* Position cards */
  .pos-card {
    background: var(--input-bg); border-radius: 4px; padding: 8px 10px; margin-bottom: 6px;
    border-left: 3px solid var(--green);
  }
  .pos-card.negative { border-left-color: var(--red-light); }
  .pos-top { display: flex; justify-content: space-between; font-size: 11px; font-weight: 700; }
  .pos-bottom { display: flex; justify-content: space-between; font-size: 9px; color: var(--dim); margin-top: 3px; }

  /* Big toggle button */
  .btn-toggle {
    width: 100%; padding: 14px; border: none; border-radius: 6px;
    font-size: 15px; font-weight: 700; cursor: pointer;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    transition: all .2s; margin-top: auto;
  }
  .btn-start { background: #2563eb; color: white; }
  .btn-start:hover { background: #1d4ed8; }
  .btn-stop { background: var(--red); color: white; }
  .btn-stop:hover { background: #b91c1c; }

  /* CENTER */
  .center { flex: 1; display: flex; flex-direction: column; min-width: 0; background: var(--center); }
  .center-hdr {
    height: 36px; background: var(--sidebar); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; padding: 0 14px; flex-shrink: 0;
  }
  .log-area {
    flex: 1; padding: 12px 14px; overflow-y: auto;
    font-family: 'Ubuntu Mono', 'Courier New', monospace; font-size: 11.5px;
    line-height: 1.7; color: #888;
  }
  .log-area .l-blue { color: var(--blue); }
  .log-area .l-green { color: var(--green-light); font-weight: 600; }
  .log-area .l-dim { color: #666; }
  .log-area .l-gray { color: #999; }
  .log-box {
    background: var(--win); padding: 10px 12px; border-radius: 4px;
    border: 1px solid var(--border); margin: 6px 0; font-size: 12px; color: #ccc;
  }
  .log-box .tag { font-weight: 700; margin-right: 6px; }
  .log-box .tag-hold { color: var(--yellow); }
  .log-box .tag-buy { color: var(--green-light); }
  .log-box .tag-sell { color: var(--red-light); }
  .log-pulse { animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .4; } }

  /* RIGHT */
  .right {
    width: 260px; background: var(--sidebar);
    border-left: 1px solid var(--border);
    display: flex; flex-direction: column; flex-shrink: 0;
  }
  .right-hdr {
    height: 36px; background: var(--sidebar);
    display: flex; align-items: center; padding: 0 14px;
    border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .trades-list { flex: 1; overflow-y: auto; }
  .trade-item {
    padding: 10px 14px; border-bottom: 1px solid #333;
    transition: background .15s; cursor: default;
  }
  .trade-item:hover { background: var(--win); }
  .trade-top { display: flex; justify-content: space-between; font-size: 10px; color: var(--dim); }
  .trade-top .act-buy { color: var(--green-light); font-weight: 600; }
  .trade-top .act-sell { color: var(--red-light); font-weight: 600; }
  .trade-top .act-hold { color: var(--yellow); font-weight: 600; }
  .trade-bot { display: flex; justify-content: space-between; margin-top: 4px; }
  .trade-bot .ticker { font-size: 13px; font-weight: 700; }
  .trade-bot .total { font-size: 12px; font-weight: 500; }

  /* FOOTER */
  .footer {
    height: 22px; background: var(--footer); border-top: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 12px; font-size: 9px; color: var(--dimmer); flex-shrink: 0;
  }
  .footer-left { display: flex; gap: 16px; }
  .fc-green { color: var(--green); }
</style>
</head>
<body>

<!-- TITLE BAR -->
<div class="titlebar">
  <div class="titlebar-left">
    <div class="dots">
      <div class="dot dot-r"></div>
      <div class="dot dot-y"></div>
      <div class="dot dot-g"></div>
    </div>
    <span class="titlebar-title">MOEX AI Trader</span>
  </div>
  <div class="status-ind">
    <div class="status-dot" id="statusDot"></div>
    <span id="statusText">Остановлен</span>
  </div>
</div>

<!-- MAIN -->
<div class="main">

  <!-- LEFT -->
  <div class="left">
    <div class="section-title">⚙ Настройки</div>

    <div class="form-label">OpenRouter API Token</div>
    <input class="form-input" id="inToken" type="password" placeholder="sk-or-v1-..." />

    <div class="form-label">ID модели (OpenRouter)</div>
    <input class="form-input" id="inModel" type="text" placeholder="openai/gpt-4o-mini" />

    <div class="form-label">Таймфрейм</div>
    <select class="form-select" id="inTF">
      <option value="3h">3 часа</option>
      <option value="6h">6 часов</option>
      <option value="1d">1 день</option>
    </select>

    <button class="btn-save" onclick="saveSettings()">💾 Сохранить настройки</button>
    <button class="btn-save" style="margin-top: 10px; background: var(--blue);" onclick="checkBrain(event)">🧠 Проверить доступ к ИИ</button>

    <div class="sep"></div>

    <div class="section-title">Баланс счёта</div>
    <div class="balance-value" id="balance">100 000.00 ₽</div>

    <div class="section-title">Открытые позиции</div>
    <div id="positions"></div>

    <button class="btn-toggle btn-start" id="toggleBtn" onclick="toggleBot()">▶ Запустить бота</button>
  </div>

  <!-- CENTER -->
  <div class="center">
    <div class="center-hdr">
      <div class="section-title" style="margin:0">📋 Лог ИИ</div>
    </div>
    <div class="log-area" id="logArea"></div>
  </div>

  <!-- RIGHT -->
  <div class="right">
    <div class="right-hdr">
      <div class="section-title" style="margin:0">📊 История сделок</div>
    </div>
    <div class="trades-list" id="tradesList">
      <div style="text-align:center;color:#666;padding:40px 20px;font-size:12px;">
        Пока сделок нет.<br>Запустите бота.
      </div>
    </div>
  </div>

</div>

<!-- FOOTER -->
<div class="footer">
  <div class="footer-left">
    <span>API: <span id="footerApi" class="fc-green">Ожидание</span></span>
  </div>
  <span>MOEX AI Trader v2</span>
</div>

<script>
let isRunning = false;
let lastLogCount = 0;

// Load saved settings on start
async function loadSettings() {
  const raw = await pywebview.api.get_settings();
  const s = JSON.parse(raw);
  document.getElementById('inToken').value = s.token || '';
  document.getElementById('inModel').value = s.model || 'openai/gpt-4o-mini';
  document.getElementById('inTF').value = s.timeframe || '3h';
}

async function saveSettings() {
  const token = document.getElementById('inToken').value;
  const model = document.getElementById('inModel').value;
  const tf = document.getElementById('inTF').value;
  await pywebview.api.save_settings(token, model, tf);
}

async function toggleBot() {
  if (!isRunning) {
    await pywebview.api.start_bot();
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

function colorizeLog(line) {
  // Detect log type for coloring
  if (line.includes('AI Decision:') || line.includes('Ticker:') || line.includes('RSI') || line.includes('SMA')) {
    return `<span class="l-blue">${esc(line)}</span>`;
  }
  if (line.includes('✅') || line.includes('order filled') || line.includes('Ордер исполнен') || line.includes('executed')) {
    return `<span class="l-green">${esc(line)}</span>`;
  }
  if (line.includes('🟢 BUY') || line.includes('BUY')) {
    // Check if it's a decision box
    if (line.includes('Reasoning:') || line.includes('💡')) {
      return `<div class="log-box"><span class="tag tag-buy">🟢 BUY</span>${esc(line.replace(/.*BUY/, ''))}</div>`;
    }
  }
  if (line.includes('🔴 SELL') || line.includes('SELL')) {
    if (line.includes('Reasoning:') || line.includes('💡')) {
      return `<div class="log-box"><span class="tag tag-sell">🔴 SELL</span>${esc(line.replace(/.*SELL/, ''))}</div>`;
    }
  }
  if (line.includes('🟡 HOLD') || line.includes('HOLD')) {
    if (line.includes('Reasoning:') || line.includes('💡')) {
      return `<div class="log-box"><span class="tag tag-hold">🟡 HOLD</span>${esc(line.replace(/.*HOLD/, ''))}</div>`;
    }
  }
  if (line.includes('⏳') || line.includes('Ожидание')) {
    return `<span class="l-dim log-pulse">${esc(line)}</span>`;
  }
  if (line.includes('⚠') || line.includes('❌')) {
    return `<span style="color:var(--red-light)">${esc(line)}</span>`;
  }
  return `<span class="l-gray">${esc(line)}</span>`;
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

async function poll() {
  try {
    const raw = await pywebview.api.get_status();
    const d = JSON.parse(raw);

    isRunning = d.running;

    // Status
    const dot = document.getElementById('statusDot');
    const stxt = document.getElementById('statusText');
    const btn = document.getElementById('toggleBtn');
    const fapi = document.getElementById('footerApi');

    if (d.running) {
      dot.className = 'status-dot on';
      stxt.textContent = 'Работает';
      stxt.style.color = 'var(--green)';
      btn.className = 'btn-toggle btn-stop';
      btn.innerHTML = '⏹ Остановить бота';
      fapi.textContent = 'Connected';
      fapi.className = 'fc-green';
    } else {
      dot.className = 'status-dot';
      stxt.textContent = 'Остановлен';
      stxt.style.color = 'var(--dim)';
      btn.className = 'btn-toggle btn-start';
      btn.innerHTML = '▶ Запустить бота';
      fapi.textContent = 'Ожидание';
      fapi.className = '';
    }

    // Balance
    document.getElementById('balance').textContent =
      d.balance.toLocaleString('ru-RU', {minimumFractionDigits: 2}) + ' ₽';

    // Positions
    const posEl = document.getElementById('positions');
    if (d.positions.length === 0) {
      posEl.innerHTML = '<div style="color:#666;font-size:11px;padding:6px 0;">Нет позиций</div>';
    } else {
      posEl.innerHTML = d.positions.map(p => {
        const cls = p.pnl >= 0 ? '' : 'negative';
        const pctColor = p.pct >= 0 ? 'var(--green-light)' : 'var(--red-light)';
        const sign = p.pnl > 0 ? '+' : '';
        return `<div class="pos-card ${cls}">
          <div class="pos-top">
            <span>${p.name} x ${p.qty}</span>
            <span style="color:${pctColor}">${p.pct > 0 ? '+' : ''}${p.pct}%</span>
          </div>
          <div class="pos-bottom">
            <span>Цена: ${p.price.toFixed(2)}</span>
            <span>PnL: ${sign}${p.pnl.toFixed(2)} ₽</span>
          </div>
        </div>`;
      }).join('');
    }

    // Logs
    if (d.logs.length !== lastLogCount) {
      const logEl = document.getElementById('logArea');
      // Only append new lines
      const newLogs = d.logs.slice(lastLogCount);
      for (const line of newLogs) {
        logEl.innerHTML += colorizeLog(line) + '<br>';
      }
      logEl.scrollTop = logEl.scrollHeight;
      lastLogCount = d.logs.length;
    }

    // Trades
    if (d.trades.length > 0) {
      const tEl = document.getElementById('tradesList');
      tEl.innerHTML = d.trades.map(t => {
        const actCls = t.action === 'BUY' ? 'act-buy' : t.action === 'SELL' ? 'act-sell' : 'act-hold';
        const qtyText = t.qty > 0 ? `${t.ticker} x ${t.qty}` : t.ticker;
        const totalText = t.total > 0 ? `${t.total.toLocaleString('ru-RU')} ₽` : '';
        return `<div class="trade-item">
          <div class="trade-top">
            <span>${t.time.substring(5)}</span>
            <span class="${actCls}">${t.action}</span>
          </div>
          <div class="trade-bot">
            <span class="ticker">${qtyText}</span>
            <span class="total">${totalText}</span>
          </div>
        </div>`;
      }).join('');
    }

  } catch(e) {}
}

// Init
window.addEventListener('pywebviewready', () => {
  loadSettings();
  setInterval(poll, 500);
});
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────
if __name__ == "__main__":
    api = Api()
    window = webview.create_window(
        "MOEX AI Trader",
        html=HTML,
        js_api=api,
        width=1100,
        height=700,
        min_size=(900, 550),
        background_color="#1e1e1e",
        frameless=False,
        easy_drag=False,
    )
    webview.start(debug=False)
