from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

from src.config.crypto import encrypt_value, decrypt_value

APP_NAME = "tickhud"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
DATA_DIR = Path.home() / ".local" / "share" / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "exchange": "okx",
    "api_key": "",
    "api_secret": "",
    "api_password": "",
    "window_x": None,
    "window_y": None,
    "opacity": 0.85,
    "refresh_ms": 100,
}

_SECRET_KEYS = ("api_key", "api_secret", "api_password")


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        stored = json.loads(CONFIG_FILE.read_text())
        cfg.update(stored)
    for k in _SECRET_KEYS:
        if cfg.get(k):
            cfg[k] = decrypt_value(cfg[k])
    return cfg


def save_config(cfg: dict):
    ensure_dirs()
    out = dict(cfg)
    for k in _SECRET_KEYS:
        if out.get(k):
            out[k] = encrypt_value(out[k])
    CONFIG_FILE.write_text(json.dumps(out, indent=2))


def get_db_path() -> Path:
    ensure_dirs()
    return DATA_DIR / "ledger.db"
