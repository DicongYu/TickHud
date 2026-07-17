from __future__ import annotations

import json
import os
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path

from src.config.crypto import encrypt_value, decrypt_value

APP_NAME = "tickhud"
BASE_CONFIG_DIR = Path.home() / ".config" / APP_NAME
BASE_DATA_DIR = Path.home() / ".local" / "share" / APP_NAME
CONFIG_DIR = Path(os.environ.get("TICKHUD_CONFIG_DIR", str(BASE_CONFIG_DIR)))
DATA_DIR = Path(os.environ.get("TICKHUD_DATA_DIR", str(BASE_DATA_DIR)))
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
    "alarms": [
        {"market": "Tokyo",   "summer": "07:00", "winter": "07:00", "sound": "", "enabled": False},
        {"market": "London",  "summer": "15:00", "winter": "16:00", "sound": "", "enabled": False},
        {"market": "New York","summer": "20:00", "winter": "21:00", "sound": "", "enabled": False},
    ],
    "periodic_reminder": {
        "enabled": False,
        "interval": 5,
        "sound": "",
    },
}

_SECRET_KEYS = ("api_key", "api_secret", "api_password")


def is_dst() -> bool:
    """Simple DST detection for US/EU (Northern Hemisphere)"""
    m = datetime.now().month
    return 4 <= m <= 10


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


def get_log_path() -> Path:
    ensure_dirs()
    return DATA_DIR / "tickhud.log"


BEEP_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "beep.wav"
