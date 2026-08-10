#!/usr/bin/env python3
"""
tui.py — MOEX AI Trader v3 — Terminal UI (Textual).
Интерактивный интерфейс с прокруткой, настройками и логами.
"""

import sys
import requests
import dotenv

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import Header, Footer, DataTable, RichLog, Static, Input, Button, Label, TextArea
from textual.screen import ModalScreen

from config import settings, _env_path
from bot_engine import engine

class EditTickersScreen(ModalScreen):
    CSS = """
    EditTickersScreen { align: center middle; }
    #dialog { padding: 1 2; background: #1a1a22; border: solid #3a3a48; width: 60; height: 12; }
    Horizontal { height: auto; margin-top: 1; }
    Button { margin-right: 2; margin-top: 1; }
    """
    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label("Введите тикеры (через запятую):", classes="bold")
            yield Input(value=",".join(settings.tickers), id="in_tickers")
            with Horizontal():
                yield Button("Сохранить", variant="success", id="save")
                yield Button("Отмена", variant="error", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            val = self.query_one("#in_tickers", Input).value
            t = [x.strip().upper() for x in val.split(",") if x.strip()]
            if t:
                settings.tickers = t
                dotenv.set_key(str(_env_path), "TICKERS", ",".join(t))
        self.dismiss()

class EditStrategyScreen(ModalScreen):
    CSS = """
    EditStrategyScreen { align: center middle; }
    #dialog_str { padding: 1 2; background: #1a1a22; border: solid #3a3a48; width: 80; height: 20; }
    Horizontal { height: auto; margin-top: 1; }
    Button { margin-right: 2; margin-top: 1; }
    """
    def compose(self) -> ComposeResult:
        with Container(id="dialog_str"):
            yield Label("Стратегия ИИ:", classes="bold")
            yield TextArea(text=settings.user_strategy, id="in_strategy")
            with Horizontal():
                yield Button("Сохранить", variant="success", id="save_str")
                yield Button("Отмена", variant="error", id="cancel_str")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_str":
            val = self.query_one("#in_strategy", TextArea).text
            if val.strip():
                settings.user_strategy = val.strip()
                dotenv.set_key(str(_env_path), "USER_STRATEGY", settings.user_strategy)
        self.dismiss()

class AiCheckScreen(ModalScreen):
    CSS = """
    AiCheckScreen { align: center middle; }
    #dialog_ai { padding: 1 2; background: #1a1a22; border: solid #3a3a48; width: 60; height: 10; align: center middle; }
    """
    def compose(self) -> ComposeResult:
        with Container(id="dialog_ai"):
            yield Label("⏳ Проверка доступа к ИИ...", id="status_label")
            with Horizontal(classes="mt"):
                yield Button("Закрыть", variant="primary", id="close_btn", disabled=True)

    def on_mount(self) -> None:
        self.run_worker(self.check_ai(), exclusive=True)

    async def check_ai(self) -> None:
        lbl = self.query_one("#status_label", Label)
        btn = self.query_one("#close_btn", Button)
        try:
            url = f"{settings.llm_api_url.rstrip('/')}/chat/completions"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {settings.llm_api_key}"}
            payload = {"model": settings.llm_model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            if r.status_code == 200:
                lbl.update("[bold green]✅ Успешно:[/bold green] Доступ к ИИ установлен!")
            else:
                lbl.update(f"[bold red]❌ Ошибка {r.status_code}:[/bold red] {r.text[:50]}")
        except Exception as e:
            lbl.update(f"[bold red]❌ Системная ошибка:[/bold red] {e}")
        btn.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

class MoexApp(App):
    TITLE = "MOEX AI Trader v3"
    CSS = """
    Screen { background: #0f0f13; }
    #sidebar { width: 35; dock: left; height: 100%; border-right: solid #2f2f3a; }
    #center { width: 1fr; height: 100%; }
    #right { width: 40; dock: right; height: 100%; border-left: solid #2f2f3a; }
    
    #portfolio { height: 9; border-bottom: solid #2f2f3a; padding: 1; }
    #action_bar { height: 11; border-bottom: solid #2f2f3a; padding: 1; }
    .btn_row { height: 3; width: 100%; }
    .btn_row Button { width: 48%; margin-right: 1; min-width: 10; }
    #positions { height: 1fr; }
    
    #tickers { height: 45%; border-bottom: solid #2f2f3a; }
    #logs { height: 1fr; }
    
    #trades { height: 1fr; padding: 1; }
    
    DataTable { background: #0f0f13; }
    RichLog { background: #0f0f13; padding: 0 1; }
    """
    BINDINGS = [
        ("ctrl+c", "quit", "Выход"),
        ("ctrl+p", "command_palette", "Команды")
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static(id="portfolio")
                with Vertical(id="action_bar"):
                    with Horizontal(classes="btn_row"):
                        yield Button("▶ Пуск/Стоп", id="btn_toggle", variant="primary")
                        yield Button("🔄 Обновить", id="btn_refresh", variant="success")
                    with Horizontal(classes="btn_row"):
                        yield Button("⚙ Тикеры", id="btn_edit")
                        yield Button("🧠 Тест ИИ", id="btn_ai")
                    with Horizontal(classes="btn_row"):
                        yield Button("📝 Стратегия", id="btn_strategy")
                yield DataTable(id="positions")
            with Vertical(id="center"):
                yield DataTable(id="tickers")
                yield RichLog(id="logs", markup=True, max_lines=200)
            with Vertical(id="right"):
                yield Static(id="trades")
        yield Footer()

    def on_mount(self) -> None:
        dt_pos = self.query_one("#positions", DataTable)
        dt_pos.add_columns("Тикер", "Кол-во", "PnL")
        dt_pos.cursor_type = "row"

        dt_tick = self.query_one("#tickers", DataTable)
        dt_tick.add_columns("Тикер", "Цена", "Индикаторы", "Паттерны", "Сигнал")
        dt_tick.cursor_type = "row"

        self.last_log_count = 0
        
        # Убрали автозапуск при старте, чтобы пользователь сам нажимал S.
        
        self.set_interval(1.0, self.update_data)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn_edit":
            self.push_screen(EditTickersScreen())
        elif btn_id == "btn_strategy":
            self.push_screen(EditStrategyScreen())
        elif btn_id == "btn_ai":
            self.push_screen(AiCheckScreen())
        elif btn_id == "btn_refresh":
            engine.force_cycle()
        elif btn_id == "btn_toggle":
            if engine.is_running:
                engine.stop()
            else:
                engine.start()

    def _build_ticker_row(self, ticker, r):
        """Build a tuple of cell values for a ticker row."""
        if not r:
            return (f"[bold]{ticker}[/bold]", "—", "—", "—", "[dim]—[/dim]")

        price = f"{r.close:.2f} ₽" if r.close else "—"
        inds = []
        if r.ema50: inds.append(f"E50:{r.ema50:.1f}")
        if r.ema200: inds.append(f"[{'green' if r.close > r.ema200 else 'red'}]E200:{r.ema200:.1f}[/]")
        if r.rsi: inds.append(f"[{'green' if r.rsi < 50 else 'red'}]RSI:{r.rsi:.1f}[/]")
        inds_txt = " ".join(inds)

        patterns_txt = r.patterns_str if hasattr(r, 'patterns_str') and r.patterns_str else "[dim]—[/dim]"

        act = r.action_taken or "SKIP"
        if act == "BUY_FAILED": act = f"[bold red]{act}[/bold red]"
        elif "BUY" in act: act = f"[bold green]{act}[/bold green]"
        elif "SELL" in act: act = f"[bold red]{act}[/bold red]"
        elif "HOLD" in act: act = f"[bold yellow]{act}[/bold yellow]"
        else: act = f"[dim]{act}[/dim]"

        return (f"[bold]{ticker}[/bold]", price, inds_txt, patterns_txt, act)

    def update_data(self) -> None:
        bal = engine.broker.get_balance() if engine.broker else settings.paper_balance
        comm = engine.broker.total_commission if (engine.broker and hasattr(engine.broker, 'total_commission')) else 0
        status_txt = "[bold green]РАБОТАЕТ[/bold green]" if engine.is_running else "[bold red]ОСТАНОВЛЕН[/bold red]"
        
        port_txt = f"[bold]💼 Портфель[/bold]\nСтатус: {status_txt}\nРежим: [bold blue]{settings.trading_mode}[/bold blue]\n\n💰 Доступно: [bold green]{bal:,.2f} ₽[/bold green]\nКомиссии: [dim]{comm:,.2f} ₽[/dim]\nЦиклов: {engine.cycles_completed}\nПоследний цикл: {engine.last_cycle_time}"
        self.query_one("#portfolio", Static).update(port_txt)

        # --- Positions table: update in-place ---
        pos_dt = self.query_one("#positions", DataTable)
        new_positions = []  # list of (ticker_label, qty_str, pnl_str)
        if engine.broker:
            for t in settings.tickers:
                p = engine.broker.get_position(t)
                if p:
                    pnl = 0.0
                    for r in reversed(engine.cycle_results):
                        if r.ticker == t and r.close > 0:
                            pnl = (r.close - p.entry_price) * p.quantity
                            break
                    pnl_s = f"[green]+{pnl:.2f}[/green]" if pnl >= 0 else f"[red]{pnl:.2f}[/red]"
                    new_positions.append((f"[bold]{t}[/bold]", str(p.quantity), pnl_s))

        # For positions, just rebuild if count changed (positions change rarely)
        if not hasattr(self, '_pos_cache'):
            self._pos_cache = []
        if new_positions != self._pos_cache:
            pos_dt.clear()
            for row in new_positions:
                pos_dt.add_row(*row)
            self._pos_cache = new_positions

        # --- Tickers table: update in-place to preserve scroll/cursor ---
        tick_dt = self.query_one("#tickers", DataTable)
        latest = {r.ticker: r for r in engine.cycle_results}
        
        current_tickers = list(settings.tickers)
        columns = ["Тикер", "Цена", "Индикаторы", "Паттерны", "Сигнал"]

        # If the set of tickers changed (or first run), rebuild the table
        if not hasattr(self, '_ticker_keys'):
            self._ticker_keys = []
        if not hasattr(self, '_ticker_cell_cache'):
            self._ticker_cell_cache = {}  # {(row_key, col_name): value}

        if current_tickers != self._ticker_keys:
            # Tickers list changed — full rebuild required
            tick_dt.clear()
            self._ticker_cell_cache.clear()
            for idx, ticker in enumerate(current_tickers):
                row_key = f"{idx}_{ticker}"
                r = latest.get(ticker)
                row_data = self._build_ticker_row(ticker, r)
                tick_dt.add_row(*row_data, key=row_key)
                for col_idx, col_name in enumerate(columns):
                    self._ticker_cell_cache[(row_key, col_name)] = row_data[col_idx]
            self._ticker_keys = list(current_tickers)
        else:
            # Same tickers — only update cells whose values actually changed
            for idx, ticker in enumerate(current_tickers):
                row_key = f"{idx}_{ticker}"
                r = latest.get(ticker)
                row_data = self._build_ticker_row(ticker, r)
                try:
                    for col_idx, col_name in enumerate(columns):
                        new_val = row_data[col_idx]
                        cache_key = (row_key, col_name)
                        if self._ticker_cell_cache.get(cache_key) != new_val:
                            tick_dt.update_cell(row_key, col_name, new_val, update_width=False)
                            self._ticker_cell_cache[cache_key] = new_val
                except Exception:
                    # Row key not found — fallback to full rebuild
                    tick_dt.clear()
                    self._ticker_cell_cache.clear()
                    for i, tk in enumerate(current_tickers):
                        rk = f"{i}_{tk}"
                        rd = self._build_ticker_row(tk, latest.get(tk))
                        tick_dt.add_row(*rd, key=rk)
                        for ci, cn in enumerate(columns):
                            self._ticker_cell_cache[(rk, cn)] = rd[ci]
                    break

        log_view = self.query_one("#logs", RichLog)
        if hasattr(engine, 'total_logs_emitted'):
            if engine.total_logs_emitted > self.last_log_count:
                new_count = engine.total_logs_emitted - self.last_log_count
                # Ensure we don't try to fetch more logs than are available in the engine's list
                if new_count > len(engine.logs):
                    new_logs = engine.logs
                else:
                    new_logs = engine.logs[-new_count:] if new_count > 0 else []

                for line in new_logs:
                    style = "white"
                    if "❌" in line or "ERROR" in line or "🔴" in line or "SELL" in line or "🛑" in line:
                        style = "red"
                    elif "🟢" in line or "✅" in line or "BUY" in line:
                        style = "green"
                    elif "🟡" in line or "HOLD" in line:
                        style = "yellow"
                    elif "📊" in line or "📈" in line or "📦" in line:
                        style = "cyan"
                    elif "💡" in line or "🤖" in line:
                        style = "magenta"
                    elif "⏳" in line or "===" in line:
                        style = "dim"
                    log_view.write(f"[{style}]{line}[/{style}]")
                self.last_log_count = engine.total_logs_emitted

        trades = []
        if engine.broker and hasattr(engine.broker, 'trade_log'):
            trades = engine.broker.trade_log[-20:]
            
        t_txt = "[bold magenta]📅 Последние сделки[/bold magenta]\n\n"
        if not trades:
            t_txt += "[dim]Пока сделок нет.[/dim]"
        else:
            for t in reversed(trades):
                col = "green" if t['action'] == "BUY" else "red"
                t_txt += f"[dim]{t['time']}[/dim] [{col} bold]{t['action']}[/]\n"
                t_txt += f"[bold]{t['ticker']} ×{t['quantity']}[/bold]  {(t['price']*t['quantity']):,.0f} ₽\n"
                if t.get('pnl', 0) != 0:
                    sign = "+" if t['pnl'] > 0 else ""
                    pcol = "green" if t['pnl'] >= 0 else "red"
                    t_txt += f"[{pcol}]PnL: {sign}{t['pnl']:.2f} ₽[/{pcol}]\n"
                t_txt += "[dim]" + "─" * 20 + "[/dim]\n"
        self.query_one("#trades", Static).update(t_txt)


if __name__ == "__main__":
    app = MoexApp()
    app.run()
    engine.stop()
