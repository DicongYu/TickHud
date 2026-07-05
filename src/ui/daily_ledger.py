from __future__ import annotations

import calendar
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout, QWidget, QSizePolicy, QComboBox, QFrame,
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
        now = datetime.now()
        self._current_year = now.year
        self._current_month = now.month
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

        for row_idx, week in enumerate(month_days):
            for col_idx, (day_num, _) in enumerate(week):
                if day_num == 0:
                    continue
                cell = self._make_cell(day_num)
                self._grid.addWidget(cell, row_idx + 1, col_idx)

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

    def _combo_changed(self):
        self._current_month = self._month_combo.currentIndex() + 1
        self._current_year = int(self._year_combo.currentText())
        self._render_month()

    def _update_stats(self):
        prefix = f"{self._current_year:04d}-{self._current_month:02d}"
        pnls = [v for k, v in self._daily_pnls.items() if k.startswith(prefix) and v is not None]

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
