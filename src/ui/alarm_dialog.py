from __future__ import annotations

import os
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QTimeEdit, QLineEdit, QFileDialog, QGroupBox,
    QComboBox,
)

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from src.config.settings import load_config, save_config, is_dst, BEEP_PATH

STYLE = """
QGroupBox {
    font-family: "JetBrains Mono", "monospace";
    font-size: 13px;
    color: #f0f0f0;
    border: 1px solid #333;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QCheckBox {
    font-family: "JetBrains Mono", "monospace";
    font-size: 13px;
    color: #f0f0f0;
}
QTimeEdit {
    font-family: "JetBrains Mono", "monospace";
    font-size: 13px;
    padding: 4px;
    background: #1a1a1a;
    color: #f0f0f0;
    border: 1px solid #333;
    border-radius: 4px;
}
QLineEdit {
    font-family: "JetBrains Mono", "monospace";
    font-size: 12px;
    padding: 4px 6px;
    background: #1a1a1a;
    color: #888;
    border: 1px solid #333;
    border-radius: 4px;
}
QPushButton {
    font-family: "JetBrains Mono", "monospace";
    font-size: 12px;
    padding: 4px 10px;
    background: #1a1a1a;
    color: #f0f0f0;
    border: 1px solid #333;
    border-radius: 4px;
}
QPushButton:hover {
    background: #2a2a2a;
    border: 1px solid #555;
}
QPushButton#saveBtn {
    background: #22c55e;
    color: #000;
    border: none;
    font-weight: bold;
}
QPushButton#saveBtn:hover {
    background: #16a34a;
}
"""


class AlarmRow:
    def __init__(self, data: dict, parent=None):
        self._parent = parent
        self._player = None
        self._audio_output = None
        self.market = data["market"]
        self._enabled = QCheckBox()
        self._enabled.setChecked(data.get("enabled", False))
        self._summer = QTimeEdit()
        self._summer.setDisplayFormat("HH:mm")
        h, m = data["summer"].split(":")
        self._summer.setTime(self._summer.time().fromString(f"{h}:{m}", "HH:mm"))
        self._winter = QTimeEdit()
        self._winter.setDisplayFormat("HH:mm")
        h, m = data["winter"].split(":")
        self._winter.setTime(self._winter.time().fromString(f"{h}:{m}", "HH:mm"))
        self._sound = QLineEdit(data.get("sound", ""))
        self._sound.setPlaceholderText("None (bundled beep)")
        self._browse = QPushButton("Browse…")
        self._browse.clicked.connect(self._pick_sound)
        self._clear = QPushButton("✕")
        self._clear.setFixedWidth(24)
        self._clear.setToolTip("Reset to default")
        self._clear.clicked.connect(lambda: self._sound.setText(""))
        self._play = QPushButton("▶")
        self._play.setFixedWidth(32)
        self._play.clicked.connect(self._toggle_sound)

    def _pick_sound(self):
        fp, _ = QFileDialog.getOpenFileName(
            None, "Select Sound", "", "Audio (*.wav *.mp3);;All Files (*)"
        )
        if fp:
            self._sound.setText(fp)

    def _toggle_sound(self):
        if self._player and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.stop()
            self._cleanup_player()
            self._play.setText("▶")
            return
        sound_path = self._sound.text().strip()
        if not sound_path or not Path(sound_path).exists():
            sound_path = str(BEEP_PATH)
        if sound_path and Path(sound_path).exists():
            from PyQt6.QtCore import QUrl
            self._player = QMediaPlayer(self._parent) if self._parent else QMediaPlayer()
            self._audio_output = QAudioOutput(self._parent) if self._parent else QAudioOutput()
            self._player.setAudioOutput(self._audio_output)
            self._audio_output.setVolume(0.8)
            self._player.mediaStatusChanged.connect(self._on_media_status)
            self._player.setSource(QUrl.fromLocalFile(sound_path))
            self._player.play()
            self._play.setText("■")
        else:
            from PyQt6.QtWidgets import QApplication
            QApplication.beep()
            self._play.setText("■")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(250, lambda: self._play.setText("▶"))

    def _on_media_status(self, status):
        if self._player is None:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._cleanup_player()
            self._play.setText("▶")
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            sp = self._player.source().toString()
            self._cleanup_player()
            if sp and str(BEEP_PATH) not in sp:
                self._sound.setText("")
                self._toggle_sound()
            else:
                self._play.setText("▶")

    def _cleanup_player(self):
        self._player = None
        self._audio_output = None

    def to_dict(self) -> dict:
        return {
            "market": self.market,
            "enabled": self._enabled.isChecked(),
            "summer": self._summer.time().toString("HH:mm"),
            "winter": self._winter.time().toString("HH:mm"),
            "sound": self._sound.text(),
        }

    def widgets(self):
        return [self._enabled, self._summer, self._winter, self._sound, self._browse, self._clear, self._play]


class AlarmDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Market Alarms")
        self.setFixedSize(640, 440)
        self.setStyleSheet("background: #0d0d0d; color: #f0f0f0;" + STYLE)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        cfg = load_config()
        self._pr_player = None
        self._pr_audio = None
        self._rows = [AlarmRow(a, parent=self) for a in cfg.get("alarms", [])]
        pr = cfg.get("periodic_reminder", {"enabled": False, "interval": 5, "sound": ""})

        layout = QVBoxLayout(self)

        season = "Summer (DST)" if is_dst() else "Winter"
        info = QLabel(f"Current:  {season}")
        info.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(info)

        group = QGroupBox("Alarms")
        group_layout = QVBoxLayout(group)

        header = QHBoxLayout()
        labels = ["On", "Market", f"Time ({season})", "Sound", ""]
        for i, lbl in enumerate(labels):
            w = QLabel(lbl)
            w.setStyleSheet("font-size: 11px; color: #888;")
            if i == 3:
                w.setFixedWidth(190)
            elif i == 1:
                w.setFixedWidth(70)
            elif i == 2:
                w.setFixedWidth(110)
            elif i == 0:
                w.setFixedWidth(30)
            header.addWidget(w)
        clear_header = QLabel("")
        clear_header.setFixedWidth(24)
        header.addWidget(clear_header)
        play_header = QLabel("")
        play_header.setFixedWidth(32)
        header.addWidget(play_header)
        group_layout.addLayout(header)

        for row in self._rows:
            row_layout = QHBoxLayout()
            market_lbl = QLabel(row.market)
            market_lbl.setStyleSheet("font-size: 13px; color: #f0f0f0;")
            market_lbl.setFixedWidth(70)
            widgets = row.widgets()
            row_layout.addWidget(widgets[0])  # checkbox
            row_layout.addWidget(market_lbl)
            row_layout.addWidget(widgets[1])  # summer time
            row_layout.addWidget(widgets[2])  # winter time
            row_layout.addWidget(widgets[3], 1)  # sound path
            row_layout.addWidget(widgets[4])  # browse
            row_layout.addWidget(widgets[5])  # clear
            row_layout.addWidget(widgets[6])  # play
            group_layout.addLayout(row_layout)

        layout.addWidget(group)

        pr_group = QGroupBox("Periodic Reminder")
        pr_layout = QHBoxLayout(pr_group)

        self._pr_enabled = QCheckBox("On")
        self._pr_enabled.setChecked(pr.get("enabled", False))
        pr_layout.addWidget(self._pr_enabled)

        pr_layout.addWidget(QLabel("Every"))

        self._pr_interval = QComboBox()
        self._pr_interval.addItems(["5 min", "10 min", "15 min"])
        intervals = {5: 0, 10: 1, 15: 2}
        self._pr_interval.setCurrentIndex(intervals.get(pr.get("interval", 5), 0))
        self._pr_interval.setStyleSheet("font-size: 13px; padding: 4px;")
        pr_layout.addWidget(self._pr_interval)

        self._pr_sound = QLineEdit(pr.get("sound", ""))
        self._pr_sound.setPlaceholderText("None (bundled beep)")
        pr_layout.addWidget(self._pr_sound, 1)

        self._pr_browse = QPushButton("Browse…")
        self._pr_browse.clicked.connect(self._pr_pick_sound)
        pr_layout.addWidget(self._pr_browse)

        self._pr_clear = QPushButton("✕")
        self._pr_clear.setFixedWidth(24)
        self._pr_clear.setToolTip("Reset to default")
        self._pr_clear.clicked.connect(lambda: self._pr_sound.setText(""))
        pr_layout.addWidget(self._pr_clear)

        self._pr_play = QPushButton("▶")
        self._pr_play.setFixedWidth(32)
        self._pr_play.clicked.connect(self._pr_toggle_sound)
        pr_layout.addWidget(self._pr_play)

        layout.addWidget(pr_group)
        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("Save  ✓")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _pr_pick_sound(self):
        fp, _ = QFileDialog.getOpenFileName(
            None, "Select Sound", "", "Audio (*.wav *.mp3);;All Files (*)"
        )
        if fp:
            self._pr_sound.setText(fp)

    def _pr_toggle_sound(self):
        if self._pr_player and self._pr_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._pr_player.stop()
            self._pr_player = None
            self._pr_audio = None
            self._pr_play.setText("▶")
            return
        sound_path = self._pr_sound.text().strip()
        if not sound_path or not Path(sound_path).exists():
            sound_path = str(BEEP_PATH)
        if sound_path and Path(sound_path).exists():
            from PyQt6.QtCore import QUrl
            self._pr_player = QMediaPlayer(self)
            self._pr_audio = QAudioOutput(self)
            self._pr_player.setAudioOutput(self._pr_audio)
            self._pr_audio.setVolume(0.8)
            self._pr_player.mediaStatusChanged.connect(self._pr_on_media_status)
            self._pr_player.setSource(QUrl.fromLocalFile(sound_path))
            self._pr_player.play()
            self._pr_play.setText("■")
        else:
            from PyQt6.QtWidgets import QApplication
            QApplication.beep()
            self._pr_play.setText("■")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(250, lambda: self._pr_play.setText("▶"))

    def _pr_on_media_status(self, status):
        if self._pr_player is None:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._pr_player = None
            self._pr_audio = None
            self._pr_play.setText("▶")
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            sp = self._pr_player.source().toString()
            self._pr_player = None
            self._pr_audio = None
            if sp and str(BEEP_PATH) not in sp:
                self._pr_sound.setText("")
                self._pr_toggle_sound()
            else:
                self._pr_play.setText("▶")

    def _on_save(self):
        cfg = load_config()
        cfg["alarms"] = [r.to_dict() for r in self._rows]
        idx = self._pr_interval.currentIndex()
        cfg["periodic_reminder"] = {
            "enabled": self._pr_enabled.isChecked(),
            "interval": [5, 10, 15][idx],
            "sound": self._pr_sound.text(),
        }
        save_config(cfg)
        self.accept()
