from __future__ import annotations

import calendar
import os
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout, QWidget, QSizePolicy, QComboBox, QFrame, QMessageBox,
)

from src.db.local_store import LocalStore


_CELL_STYLE = """
QLabel {
    font-family: "JetBrains Mono", "monospace";
    font-size: 10px;
    padding: 4px;
}
"""


GREEN = "#22c55e"
RED = "#ef4444"

class DailyLedgerDialog(QDialog):
    def __init__(self, store: LocalStore, engine=None, parent=None):
        super().__init__(parent)
        self._store = store
        self._engine = engine
        now = datetime.now()
        self._current_year = now.year
        self._current_month = now.month
        rows = store.get_all_baselines()
        self._baselines = {b["date"]: b["equity_usdt"] for b in rows}
        self._realized_pnls: dict[str, float] = {}
        for b in rows:
            rp = b.get("realized_pnl")
            if rp is not None and rp != 0:
                self._realized_pnls[b["date"]] = rp
        self._daily_pnls: dict[str, float] = {}
        self._compute_pnls()

        self._today_cell: QWidget | None = None
        self._today_pnl_lbl: QLabel | None = None
        self._today_date_str: str = now.strftime("%Y-%m-%d")

        title = "Daily PnL Ledger"
        if "--test" in sys.argv or os.environ.get("TICKHUD_DATA_DIR"):
            title += " [TEST]"
        self.setWindowTitle(title)
        self.setMinimumSize(900, 680)
        self.setStyleSheet("background: #0d0d0d; color: #f0f0f0;")

        self._build_ui()
        self._render_month()

        if self._engine:
            self._refresh_timer = QTimer(self)
            self._refresh_timer.timeout.connect(self._refresh_today)
            self._refresh_timer.start(1000)

    def _refresh_today(self):
        if not self._today_pnl_lbl or not self._engine:
            return
        snap = self._engine.snapshot
        dp = snap.daily_pnl
        if dp is None:
            return
        val_txt = f"{dp:+,.2f}"
        clr = GREEN if dp >= 0 else RED
        self._today_pnl_lbl.setText(val_txt)
        self._today_pnl_lbl.setStyleSheet(f"font-size: 11px; color: {clr};")
        if self._today_cell:
            prefix = "" if self._engine.has_baseline() else "?"
            self._today_cell.setToolTip(
                f"Date:  {self._today_date_str}\n"
                f"Daily PnL: {prefix}{val_txt}"
            )
        self._update_stats()

    def _reset_ledger(self):
        ret = QMessageBox.warning(
            self, "Reset Ledger",
            "Clear all baseline, transfer, and snapshot history?\n\n"
            "This cannot be undone. Data will rebuild from the next poll cycle.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._store.clear_all()
        self._baselines.clear()
        self._realized_pnls.clear()
        self._daily_pnls.clear()
        self._render_month()

    def _compute_pnls(self):
        sorted_dates = sorted(self._realized_pnls.keys())
        prev_realized = None
        for date in sorted_dates:
            curr_realized = self._realized_pnls[date]
            if prev_realized is not None:
                self._daily_pnls[date] = round(curr_realized - prev_realized, 2)
            prev_realized = curr_realized

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 20, 32, 20)

        nav = QHBoxLayout()
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedWidth(52)
        self._prev_btn.setFixedHeight(38)
        self._prev_btn.setStyleSheet("font-size: 18px; background: #1a1a1a; border: 1px solid #333; border-radius: 4px; color: #f0f0f0;")
        self._prev_btn.clicked.connect(self._prev_month)
        nav.addWidget(self._prev_btn)

        self._month_combo = QComboBox()
        self._month_combo.addItems([calendar.month_name[m] for m in range(1, 13)])
        self._month_combo.setCurrentIndex(self._current_month - 1)
        self._month_combo.setStyleSheet("font-size: 18px; background: #1a1a1a; border: 1px solid #333; border-radius: 4px; color: #f0f0f0; padding: 6px 12px;")
        self._month_combo.currentIndexChanged.connect(self._combo_changed)
        nav.addWidget(self._month_combo)

        self._year_combo = QComboBox()
        cy = datetime.now().year
        for y in range(cy - 5, cy + 2):
            self._year_combo.addItem(str(y))
        self._year_combo.setCurrentText(str(self._current_year))
        self._year_combo.setStyleSheet("font-size: 18px; background: #1a1a1a; border: 1px solid #333; border-radius: 4px; color: #f0f0f0; padding: 6px 12px;")
        self._year_combo.currentTextChanged.connect(self._combo_changed)
        nav.addWidget(self._year_combo)

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedWidth(52)
        self._next_btn.setFixedHeight(38)
        self._next_btn.setStyleSheet("font-size: 18px; background: #1a1a1a; border: 1px solid #333; border-radius: 4px; color: #f0f0f0;")
        self._next_btn.clicked.connect(self._next_month)
        nav.addWidget(self._next_btn)

        nav.addStretch()

        reset_btn = QPushButton("× Reset Ledger")
        reset_btn.setStyleSheet("font-size: 13px; background: #1a0000; border: 1px solid #4a0000; border-radius: 4px; color: #ef4444; padding: 6px 14px;")
        reset_btn.clicked.connect(self._reset_ledger)
        nav.addWidget(reset_btn)

        layout.addLayout(nav)

        layout.addSpacing(12)

        self._grid = QGridLayout()
        self._grid.setSpacing(8)
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for col_idx, day in enumerate(days):
            lbl = QLabel(day)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 13px; color: #666; font-weight: bold; letter-spacing: 1px;")
            self._grid.addWidget(lbl, 0, col_idx)
        layout.addLayout(self._grid)
        layout.addSpacing(16)

        self._stats_bar = QHBoxLayout()
        self._stats_bar.setSpacing(12)
        self._stat_labels: dict[str, QLabel] = {}
        for key, title in [
            ("total", "Total"),
            ("win_rate", "Win Rate"),
            ("avg", "Avg"),
            ("best", "Best"),
            ("worst", "Worst"),
            ("days", "Days"),
        ]:
            card = QFrame()
            card.setStyleSheet("QFrame { background: #141414; border-radius: 6px; padding: 6px; }")
            vbox = QVBoxLayout(card)
            vbox.setContentsMargins(14, 8, 14, 8)
            vbox.setSpacing(2)
            title_lbl = QLabel(title)
            title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_lbl.setStyleSheet("font-size: 11px; color: #666;")
            vbox.addWidget(title_lbl)
            val = QLabel("—")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet("font-size: 18px; font-weight: bold;")
            vbox.addWidget(val)
            self._stat_labels[key] = val
            self._stats_bar.addWidget(card)
        layout.addLayout(self._stats_bar)

        layout.addSpacing(8)

    def _render_month(self):
        for i in reversed(range(self._grid.count())):
            item = self._grid.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if self._grid.getItemPosition(i)[0] > 0:
                    w.setParent(None)

        self._month_combo.blockSignals(True)
        self._month_combo.setCurrentIndex(self._current_month - 1)
        self._month_combo.blockSignals(False)
        self._year_combo.blockSignals(True)
        self._year_combo.setCurrentText(str(self._current_year))
        self._year_combo.blockSignals(False)

        cal = calendar.Calendar()
        month_days = cal.monthdays2calendar(self._current_year, self._current_month)

        grid_row = 1
        for week_idx, week in enumerate(month_days):
            for col_idx, (day_num, _) in enumerate(week):
                if day_num == 0:
                    continue
                cell = self._make_cell(day_num)
                self._grid.addWidget(cell, grid_row, col_idx)

            if week_idx < len(month_days) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet("color: #2a2a2a;")
                self._grid.addWidget(sep, grid_row + 1, 0, 1, 7)
                grid_row += 2
            else:
                grid_row += 1

        self._update_stats()

    def _make_cell(self, day_num: int) -> QWidget:
        date_str = f"{self._current_year:04d}-{self._current_month:02d}-{day_num:02d}"
        pnl = self._daily_pnls.get(date_str)

        w = QWidget()
        w.setFixedSize(100, 76)

        clr_bg = "#0d0d0d"
        clr_txt = "#666"
        val_txt = ""

        if pnl is not None:
            val_txt = f"{pnl:+,.2f}"
            if pnl > 0:
                clr_bg = "#0a1f0a"
                clr_txt = "#22c55e"
            elif pnl < 0:
                clr_bg = "#1f0a0a"
                clr_txt = "#ef4444"
            else:
                clr_txt = "#555"

        today = datetime.now().strftime("%Y-%m-%d")
        if date_str == today:
            clr_bg = "#1a1a2e"

        w.setStyleSheet(f"background: {clr_bg}; border-radius: 6px;")

        equity = self._baselines.get(date_str)
        tip_parts = [f"Date:  {date_str}"]
        if equity is not None:
            tip_parts.append(f"Equity: {equity:.2f} USDT")
        if pnl is not None:
            tip_parts.append(f"PnL:   {pnl:+.2f} USDT")
        else:
            tip_parts.append("PnL:   — (first day)")
        w.setToolTip("\n".join(tip_parts))

        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(4, 6, 4, 6)
        vbox.setSpacing(2)

        day_lbl = QLabel(str(day_num))
        day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        day_lbl.setStyleSheet(f"font-size: 15px; color: {clr_txt}; font-weight: bold;")
        vbox.addWidget(day_lbl)

        if val_txt:
            val_lbl = QLabel(val_txt)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setStyleSheet(f"font-size: 11px; color: {clr_txt};")
            vbox.addWidget(val_lbl)
        else:
            val_lbl = None

        if date_str == self._today_date_str:
            self._today_cell = w
            if val_lbl is None:
                val_lbl = QLabel("—")
                val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                val_lbl.setStyleSheet("font-size: 11px; color: #666;")
                vbox.addWidget(val_lbl)
            self._today_pnl_lbl = val_lbl

        return w

    def _combo_changed(self):
        self._current_month = self._month_combo.currentIndex() + 1
        self._current_year = int(self._year_combo.currentText())
        self._render_month()

    def _update_stats(self):
        prefix = f"{self._current_year:04d}-{self._current_month:02d}"
        pnls = []
        for k, v in self._daily_pnls.items():
            if k.startswith(prefix) and v is not None:
                if self._engine and k == self._today_date_str:
                    running = self._engine.snapshot.daily_pnl
                    pnls.append(running if running is not None else v)
                else:
                    pnls.append(v)

        # include today's running PnL even if not in archived daily_pnls
        if self._engine and prefix == self._today_date_str[:7] and self._today_date_str not in self._daily_pnls:
            running = self._engine.snapshot.daily_pnl
            if running is not None:
                pnls.append(running)

        if not pnls:
            for lbl in self._stat_labels.values():
                lbl.setText("—")
            return

        total = sum(pnls)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = len(wins) / len(pnls) * 100 if pnls else 0.0
        best = max(pnls)
        worst = min(pnls)

        def _set(key, text, color="#f0f0f0"):
            self._stat_labels[key].setText(text)
            self._stat_labels[key].setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")

        _set("total", f"{total:+,.2f}", "#22c55e" if total >= 0 else "#ef4444")
        _set("win_rate", f"{win_rate:.0f}%", "#f0f0f0")
        _set("avg", f"{total/len(pnls):+,.2f}", "#22c55e" if total >= 0 else "#ef4444")
        _set("best", f"{best:+,.2f}", "#22c55e")
        _set("worst", f"{worst:+,.2f}", "#ef4444")
        _set("days", str(len(pnls)), "#f0f0f0")

    def _prev_month(self):
        if self._current_month == 1:
            self._current_month = 12
            self._current_year -= 1
        else:
            self._current_month -= 1
        self._render_month()

    def _next_month(self):
        if self._current_month == 12:
            self._current_month = 1
            self._current_year += 1
        else:
            self._current_month += 1
        self._render_month()
