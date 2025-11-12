#!/usr/bin/env python3
"""Lightweight settings persistence for the Google Ads GUI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

SETTINGS_PATH = Path("settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "client_secret_path": "client_secret.json",
    "developer_token": "dz5hEkNi41PTNTMq29zclw",
    "login_customer_id": "",
    "customer_id": "488-455-0863",
    "lookback_days": 7,
    "min_first_hour_clicks": 50,
    "spike_ratio": 2.5,
}


def load_settings() -> Dict[str, Any]:
    if SETTINGS_PATH.exists():
        try:
            return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_PATH.read_text())}
        except Exception:  # noqa: BLE001
            return dict(DEFAULT_SETTINGS)
    return dict(DEFAULT_SETTINGS)


def save_settings(data: Dict[str, Any]) -> None:
    SETTINGS_PATH.write_text(json.dumps(data, indent=2))
