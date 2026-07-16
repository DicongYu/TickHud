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
from src.config.settings import DATA_DIR, load_config, is_dst

try:
    from PyQt6.QtMultimedia import QSoundEffect
except ImportError:
    QSoundEffect = None

GREEN = "#22c55e"
RED = "#ef4444"
WHITE = "#f8f8f8"
GRAY = "#555"
DIM = "#2a2a2a"
BG = "#0d0d0d"
CARD = "#141414"

BASE_W = 380
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

        self._load_alarms()

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
        op_col = QVBoxLayout()
        op_col.setContentsMargins(0, 0, 0, 0)
        op_col.setSpacing(2)
        op_col.addWidget(self._card_op)
        self._uptime_label = QLabel("--")
        self._uptime_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._uptime_label.setStyleSheet(f"font-size: {max(1, round(16 * self._scale))}px; color: {GRAY};")
        op_col.addWidget(self._uptime_label)
        cards_row.addLayout(op_col, 1)

        content.addLayout(cards_row)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(4, 0, 0, 0)

        self._status = QLabel("○ disconnected")
        self._status.setObjectName("status")
        bottom.addWidget(self._status)

        self._time_label = QLabel("--")
        fs = max(1, round(16 * self._scale))
        self._time_label.setStyleSheet(f"font-size: {fs}px; color: {GREEN};")
        bottom.addWidget(self._time_label)

        self._pr_label = QLabel("")
        self._pr_label.setStyleSheet(f"font-size: {fs}px; color: {GRAY};")
        bottom.addWidget(self._pr_label)

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
        lat = snap.latency_ms
        test_tag = "  [TEST]" if self._test_mode else ""

        pr_icon, pr_countdown = "", ""
        if self._pr_interval > 0:
            total_min = now.hour * 60 + now.minute
            next_aligned = ((total_min // self._pr_interval) + 1) * self._pr_interval
            remain = next_aligned - total_min
            remain_sec = remain * 60 - now.second
            if remain_sec < 0:
                remain_sec = 0
            m, s = divmod(remain_sec, 60)
            pr_icon = "🔔"
            pr_countdown = f"{m}:{s:02d}"

        if snap.connected:
            self._status.setText(f"● LIVE  {lat:.0f}ms{test_tag}")
            self._status.setStyleSheet(f"color: {GREEN};")
            fs = max(1, round(16 * self._scale))
            self._time_label.setText(f"{now:%H:%M:%S}")
            self._time_label.setStyleSheet(f"font-size: {fs}px; color: {GREEN};")
            self._pr_label.setText(f"{pr_icon} {pr_countdown}" if pr_icon else "")
            self._pr_label.setStyleSheet(f"font-size: {fs}px; color: {GRAY};")
            self._uptime_label.setText(f"{uptime_str}")
            self._uptime_label.setStyleSheet(f"font-size: {fs}px; color: {GRAY};")
        else:
            self._status.setText(f"○ disconnected")
            self._status.setStyleSheet(f"color: {GRAY};")
            self._time_label.clear()
            self._pr_label.clear()
            self._uptime_label.setText("--")

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
            tag = "  [TEST]" if self._test_mode else ""
            now = datetime.datetime.now()
            uptime = now - self._start_time

            pr_icon, pr_countdown = "", ""
            if self._pr_interval > 0:
                total_min = now.hour * 60 + now.minute
                next_aligned = ((total_min // self._pr_interval) + 1) * self._pr_interval
                remain = next_aligned - total_min
                remain_sec = remain * 60 - now.second
                if remain_sec < 0:
                    remain_sec = 0
                m, s = divmod(remain_sec, 60)
                pr_icon = "🔔"
                pr_countdown = f"{m}:{s:02d}"

            fs = max(1, round(16 * self._scale))
            self._status.setText(f"● LIVE  {lat:.0f}ms{tag}")
            self._status.setStyleSheet("color: #22c55e;")
            self._time_label.setText(f"{now:%H:%M:%S}")
            self._time_label.setStyleSheet(f"font-size: {fs}px; color: {GREEN};")
            self._pr_label.setText(f"{pr_icon} {pr_countdown}" if pr_icon else "")
            self._pr_label.setStyleSheet(f"font-size: {fs}px; color: {GRAY};")
            self._uptime_label.setText(f"{str(uptime).split('.')[0]}")
            self._uptime_label.setStyleSheet(f"font-size: {fs}px; color: {GRAY};")

    def _load_alarms(self):
        self._alarms: list[dict] = []
        self._alarm_sound = None
        self._alarm_fired: set[str] = set()
        self._pr_interval = 0
        self._pr_sound = ""
        cfg = load_config()
        for a in cfg.get("alarms", []):
            if a.get("enabled"):
                self._alarms.append(a)
        pr = cfg.get("periodic_reminder", {})
        if pr.get("enabled"):
            self._pr_interval = pr.get("interval", 5)
            self._pr_sound = pr.get("sound", "")
        if QSoundEffect is not None:
            self._alarm_sound = QSoundEffect(self)
            self._alarm_sound.setVolume(0.8)
        self._alarm_timer = QTimer(self)
        self._alarm_timer.timeout.connect(self._alarm_tick)
        self._alarm_timer.start(1000)

    def _alarm_tick(self):
        now = datetime.datetime.now()
        hm = now.strftime("%H:%M")
        dst = is_dst()

        # Market open alarms
        for a in self._alarms:
            target = a["summer"] if dst else a["winter"]
            mkey = f"{a['market']}_{target}"
            if hm == target:
                if mkey not in self._alarm_fired:
                    self._alarm_fired.add(mkey)
                    self._play_alarm(a.get("sound", ""), a["market"])
            else:
                self._alarm_fired.discard(mkey)

        # Periodic reminder (00:00-aligned)
        if self._pr_interval > 0:
            total_min = now.hour * 60 + now.minute
            if total_min % self._pr_interval == 0 and now.second < 3:
                pkey = f"pr_{total_min}"
                if pkey not in self._alarm_fired:
                    self._alarm_fired.add(pkey)
                    self._play_alarm(self._pr_sound, f"{self._pr_interval}min")
        # Cleanup stale periodic keys (keep only current and future)
        now_min = now.hour * 60 + now.minute
        self._alarm_fired = {k for k in self._alarm_fired if not k.startswith("pr_") or int(k.split("_")[1]) >= now_min - 1}

    def _play_alarm(self, sound_path: str, market: str):
        self._status.setText(f"🔔 {market} open!")
        self._status.setStyleSheet("color: #facc15;")
        QTimer.singleShot(3000, self._restore_status)
        if sound_path and QSoundEffect is not None and Path(sound_path).exists():
            from PyQt6.QtCore import QUrl
            self._alarm_sound.setSource(QUrl.fromLocalFile(sound_path))
            self._alarm_sound.play()
        else:
            import sys
            sys.stdout.write(f"\a{market} open!\n")

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
