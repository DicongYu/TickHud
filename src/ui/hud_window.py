from __future__ import annotations

import datetime
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontDatabase, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QSizeGrip, QApplication,
)

from src.engine.data_engine import DataEngine
from src.ui.settings_dialog import SettingsDialog
from src.ui.daily_ledger import DailyLedgerDialog
from src.db.local_store import LocalStore
from src.config.settings import DATA_DIR

GREEN = "#22c55e"
RED = "#ef4444"
WHITE = "#f8f8f8"
GRAY = "#555"
DIM = "#2a2a2a"
BG = "#0d0d0d"
CARD = "#141414"

BASE_W = 480
BASE_H = 100

def _gen_style(s: float = 1.0) -> str:
    def S(v: float) -> str:
        return f"{max(1, round(v * s))}px"

    return f"""
QWidget#central {{
    background: {BG};
}}
QWidget#card {{
    background: {CARD};
    border-radius: {S(6)};
}}
QLabel.label {{
    font-family: "JetBrains Mono", "monospace";
    font-size: {S(8)};
    color: {GRAY};
    padding: 0;
    margin: 0;
    letter-spacing: 1px;
}}
QLabel.value {{
    font-family: "JetBrains Mono", "monospace";
    font-weight: bold;
    color: {WHITE};
    padding: 0;
    margin: 0;
}}
QLabel.pct {{
    font-family: "JetBrains Mono", "monospace";
    font-size: {S(11)};
    font-weight: bold;
    padding: 0;
    margin: 0;
}}
QLabel#valCard {{
    font-family: "JetBrains Mono", "monospace";
    font-size: {S(14)};
    font-weight: bold;
    padding: 0;
    margin: 0;
}}
QLabel#timePct {{
    font-family: "JetBrains Mono", "monospace";
    font-size: {S(7)};
    font-weight: bold;
    color: {GRAY};
    padding: 0;
    margin: 0;
}}
QLabel#status {{
    font-family: "JetBrains Mono", "monospace";
    font-size: {S(8)};
}}
QPushButton#topBtn {{
    font-family: "JetBrains Mono", "monospace";
    font-size: {S(11)};
    color: {GRAY};
    background: transparent;
    border: none;
    padding: {S(2)} {S(5)};
}}
QPushButton#topBtn:hover {{
    color: {WHITE};
    background: {DIM};
    border-radius: {S(4)};
}}
QPushButton#closeBtn {{
    font-family: "JetBrains Mono", "monospace";
    font-size: {S(11)};
    color: {GRAY};
    background: transparent;
    border: none;
    padding: {S(2)} {S(8)};
}}
QPushButton#closeBtn:hover {{
    color: {RED};
    background: {DIM};
    border-radius: {S(4)};
}}
"""


class Card(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)

        lbl = QLabel(label)
        lbl.setProperty("class", "label")
        layout.addWidget(lbl)

        self._val = QLabel("--")
        self._val.setObjectName("valCard")
        layout.addWidget(self._val)

        self._pct = QLabel("")
        self._pct.setProperty("class", "pct")
        layout.addWidget(self._pct)

        self._prev_val: str | None = None

    def update(self, value: str, pct: str, color: str):
        if value != self._prev_val:
            self._val.setText(value)
            self._prev_val = value
        self._val.setStyleSheet(f"color: {WHITE};")
        self._pct.setText(pct)
        self._pct.setStyleSheet(f"color: {color};")


class HudWindow(QMainWindow):
    def __init__(self, engine: DataEngine, store: LocalStore, test_mode: bool = False):
        super().__init__()
        self._engine = engine
        self._store = store
        self._test_mode = test_mode
        self._start_time = datetime.datetime.now()

        self._cmd_file = DATA_DIR / "cmd"

        self._init_font()
        self._setup_window()
        self._build_ui()
        self._start_timer()

    @staticmethod
    def _init_font():
        try:
            for _fp in (
                "/usr/share/fonts/truetype/jetbrains/JetBrainsMono-Regular.ttf",
                "/usr/share/fonts/JetBrainsMono-Regular.ttf",
                "/usr/local/share/fonts/JetBrainsMono-Regular.ttf",
            ):
                if __import__("os").path.exists(_fp):
                    QFontDatabase.addApplicationFont(_fp)
                    break
        except Exception:
            pass

    def _setup_window(self):
        self.setWindowTitle("TickHUD")
        title = "TickHUD"
        if self._test_mode:
            title += " [TEST]"
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(BASE_W, BASE_H)
        self.setMaximumSize(BASE_W * 2, BASE_H * 2)
        self.resize(BASE_W, BASE_H)
        self._center_on_screen()
        self._scale = 1.0

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2
            y = (geo.height() - self.height()) // 2
            self.move(x, y)

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 2, 0, 0)

        self._ledger_btn = QPushButton("📅")
        self._ledger_btn.setObjectName("topBtn")
        self._ledger_btn.setToolTip("Daily PnL Ledger")
        self._ledger_btn.clicked.connect(self._open_ledger)
        top_bar.addWidget(self._ledger_btn)

        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setObjectName("topBtn")
        self._settings_btn.setToolTip("Settings")
        self._settings_btn.clicked.connect(self._open_settings)
        top_bar.addWidget(self._settings_btn)

        top_bar.addStretch()
        self._close_btn = QPushButton("✕")
        self._close_btn.setObjectName("closeBtn")
        self._close_btn.clicked.connect(self.close)
        top_bar.addWidget(self._close_btn)

        root.addLayout(top_bar)

        content = QVBoxLayout()
        content.setContentsMargins(8, 0, 8, 6)
        content.setSpacing(4)

        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(6)

        self._card_eq = Card("EQUITY")
        cards_row.addWidget(self._card_eq, 1)

        self._card_dp = Card("DAILY PnL")
        cards_row.addWidget(self._card_dp, 1)

        self._card_op = Card("OPEN PnL")
        cards_row.addWidget(self._card_op, 1)

        self._card_time = Card("UTC+8")
        self._card_time._pct.setObjectName("timePct")
        cards_row.addWidget(self._card_time, 1)

        content.addLayout(cards_row)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(4, 0, 0, 0)

        self._status = QLabel("○ disconnected")
        self._status.setObjectName("status")
        bottom.addWidget(self._status)

        bottom.addStretch()

        self._grip = QSizeGrip(self)
        bottom.addWidget(self._grip)

        content.addLayout(bottom)
        root.addLayout(content)

        self._apply_scale()

    def _apply_scale(self):
        w = self.width()
        h = self.height()
        s = min(w / BASE_W, h / BASE_H)
        if abs(s - 1.0) < 0.05:
            s = 1.0
        self._scale = s
        self.setStyleSheet(_gen_style(s))

    def resizeEvent(self, event):
        w = self.width()
        h = self.height()
        mw = self.minimumWidth()
        Mw = self.maximumWidth()
        mh = self.minimumHeight()
        Mh = self.maximumHeight()
        if w < mw or w > Mw or h < mh or h > Mh:
            self.resize(max(mw, min(w, Mw)), max(mh, min(h, Mh)))
            return
        super().resizeEvent(event)
        self._apply_scale()

    def _start_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_data)
        self._timer.start(100)

        if self._test_mode:
            self._cmd_timer = QTimer(self)
            self._cmd_timer.timeout.connect(self._poll_cmd)
            self._cmd_timer.start(300)

    def _poll_data(self):
        snap = self._engine.snapshot

        self._card_eq.update(
            f"{snap.equity:,.2f}",
            "",
            WHITE,
        )

        dp = snap.daily_pnl
        dp_arrow = "▲" if dp >= 0 else "▼"
        dp_color = GREEN if dp >= 0 else RED
        prefix = "" if self._engine.has_baseline() else "?"
        self._card_dp.update(
            f"{prefix}{dp:+,.2f}",
            f"{dp_arrow} {abs(snap.daily_pnl_pct):.2f}%",
            dp_color,
        )

        op = snap.open_pnl
        op_arrow = "▲" if op >= 0 else "▼"
        op_color = GREEN if op >= 0 else RED
        self._card_op.update(
            f"{op:+,.2f}",
            f"{op_arrow} {abs(snap.open_pnl_pct):.2f}%",
            op_color,
        )

        now = datetime.datetime.now()
        uptime = now - self._start_time
        uptime_str = str(uptime).split(".")[0]
        self._card_time.update(
            f"{now:%H:%M:%S}",
            f"{uptime_str}",
            GRAY,
        )

        now_str = now.strftime("%H:%M")
        lat = snap.latency_ms
        test_tag = "  [TEST]" if self._test_mode else ""
        if snap.connected:
            self._status.setText(f"● LIVE  {now_str}  {lat:.0f}ms{test_tag}")
            self._status.setStyleSheet(f"color: {GREEN};")
        else:
            self._status.setText(f"○ disconnected")
            self._status.setStyleSheet(f"color: {GRAY};")

    def _open_settings(self):
        d = SettingsDialog(self)
        d.exec()

    def _open_ledger(self):
        d = DailyLedgerDialog(self._store, engine=self._engine, parent=self)
        d.exec()

    def _poll_cmd(self):
        try:
            if not self._cmd_file.exists():
                return
            raw = self._cmd_file.read_text().strip()
            if not raw:
                return
            self._cmd_file.write_text("")
            parts = raw.split(maxsplit=1)
            cmd = parts[0]
            handler = None
            if cmd == "close_half":
                handler = self._engine.close_half
            elif cmd == "close_all":
                handler = self._engine.close_all
            elif cmd == "reset":
                handler = self._engine.reset
            elif cmd == "reset_open":
                handler = self._engine.reset_open
            if handler:
                handler()
                s = self._engine.snapshot
                self._status.setText(f"{cmd} → OPEN {s.open_pnl:+.1f}, DAILY {s.daily_pnl:+.1f}")
                self._status.setStyleSheet("color: #22c55e;")
                QTimer.singleShot(2000, self._restore_status)
        except Exception:
            pass

    def _restore_status(self):
        lat = self._engine.snapshot.latency_ms
        if self._engine.snapshot.connected:
            now = datetime.datetime.now().strftime("%H:%M")
            tag = "  [TEST]" if self._test_mode else ""
            self._status.setText(f"● LIVE  {now}  {lat:.0f}ms{tag}")
            self._status.setStyleSheet("color: #22c55e;")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, "_drag_pos"):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
