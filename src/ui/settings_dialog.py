from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QFormLayout,
)

from src.config.settings import load_config, save_config


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TickHUD Settings")
        self.setFixedSize(560, 380)
        self.setStyleSheet("background: #0d0d0d; color: #f0f0f0;")
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        cfg = load_config()

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        style = """
        QComboBox, QLineEdit {
            font-family: "JetBrains Mono", "monospace";
            font-size: 13px;
            padding: 6px 8px;
            background: #1a1a1a;
            color: #f0f0f0;
            border: 1px solid #333;
            border-radius: 4px;
        }
        QComboBox:hover, QLineEdit:hover {
            border: 1px solid #555;
        }
        QPushButton {
            font-family: "JetBrains Mono", "monospace";
            font-size: 13px;
            padding: 8px 20px;
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
        QLabel {
            font-family: "JetBrains Mono", "monospace";
            font-size: 12px;
            color: #888;
        }
        """

        self._exchange = QComboBox()
        self._exchange.addItems(["okx", "binance", "bybit"])
        self._exchange.setCurrentText(cfg.get("exchange", "okx"))
        self._exchange.setStyleSheet(style)
        form.addRow("Exchange:", self._exchange)

        self._api_key = QLineEdit(cfg.get("api_key", ""))
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("API Key")
        self._api_key.setStyleSheet(style)
        form.addRow("API Key:", self._api_key)

        self._api_secret = QLineEdit(cfg.get("api_secret", ""))
        self._api_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_secret.setPlaceholderText("API Secret")
        self._api_secret.setStyleSheet(style)
        form.addRow("API Secret:", self._api_secret)

        self._api_password = QLineEdit(cfg.get("api_password", ""))
        self._api_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_password.setPlaceholderText("Passphrase (if required)")
        self._api_password.setStyleSheet(style)
        form.addRow("Password:", self._api_password)

        layout.addLayout(form)
        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("Save  ✓")
        save_btn.setObjectName("saveBtn")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _on_save(self):
        cfg = load_config()
        cfg["exchange"] = self._exchange.currentText()
        cfg["api_key"] = self._api_key.text().strip()
        cfg["api_secret"] = self._api_secret.text().strip()
        cfg["api_password"] = self._api_password.text().strip()
        save_config(cfg)
        self.accept()
