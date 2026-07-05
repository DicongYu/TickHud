from __future__ import annotations

import calendar
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout, QWidget, QSizePolicy,
)

from src.db.local_store import LocalStore


_CELL_STYLE = """
QLabel {
    font-family: "JetBrains Mono", "monospace";
    font-size: 10px;
    padding: 4px;
}
"""


class DailyLedgerDialog(QDialog):
    def __init__(self, store: LocalStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._current_year = datetime.now().year
        self._current_month = datetime.now().month
        self._baselines = {b["date"]: b["equity_usdt"] for b in store.get_all_baselines()}
        self._daily_pnls: dict[str, float] = {}
        self._compute_pnls()

        self.setWindowTitle("Daily PnL Ledger")
        self.setMinimumSize(900, 680)
        self.setStyleSheet("background: #0d0d0d; color: #f0f0f0;")

        self._build_ui()
        self._render_month()

    def _compute_pnls(self):
        sorted_dates = sorted(self._baselines.keys())
        for i in range(1, len(sorted_dates)):
            prev_date = sorted_dates[i - 1]
            curr_date = sorted_dates[i]
            eq_prev = self._baselines[prev_date]
            eq_curr = self._baselines[curr_date]
            net = self._store.get_transfer_sum_since(prev_date + "T00:00:00")
            self._daily_pnls[curr_date] = round(eq_curr - eq_prev - net, 2)

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

        self._title = QLabel()
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet("font-size: 24px; font-weight: bold;")
        nav.addWidget(self._title, 1)

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedWidth(52)
        self._next_btn.setFixedHeight(38)
        self._next_btn.setStyleSheet("font-size: 18px; background: #1a1a1a; border: 1px solid #333; border-radius: 4px; color: #f0f0f0;")
        self._next_btn.clicked.connect(self._next_month)
        nav.addWidget(self._next_btn)
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
        layout.addStretch()

    def _render_month(self):
        for i in reversed(range(self._grid.count())):
            item = self._grid.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if self._grid.getItemPosition(i)[0] > 0:
                    w.setParent(None)

        self._title.setText(f"{calendar.month_name[self._current_month]} {self._current_year}")

        cal = calendar.Calendar()
        month_days = cal.monthdays2calendar(self._current_year, self._current_month)

        for row_idx, week in enumerate(month_days):
            for col_idx, (day_num, _) in enumerate(week):
                if day_num == 0:
                    continue
                cell = self._make_cell(day_num)
                self._grid.addWidget(cell, row_idx + 1, col_idx)

    def _make_cell(self, day_num: int) -> QWidget:
        date_str = f"{self._current_year:04d}-{self._current_month:02d}-{day_num:02d}"
        pnl = self._daily_pnls.get(date_str)

        w = QWidget()
        w.setFixedSize(100, 76)

        clr_bg = "#0d0d0d"
        clr_txt = "#666"
        val_txt = ""

        if pnl is not None:
            val_txt = f"{pnl:+,.0f}"
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

        return w

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
