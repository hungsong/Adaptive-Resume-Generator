# -*- coding: utf-8 -*-
"""Browser preference and external link opening."""
from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

from core.config import load_config, save_config


COMMON_BROWSERS = (
    ("edge", "Microsoft Edge", (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    )),
    ("chrome", "Google Chrome", (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    )),
    ("firefox", "Mozilla Firefox", (
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    )),
)


def detect_browsers() -> list[dict]:
    found = [{"key": "system", "name": "系统默认浏览器", "path": ""}]
    for key, name, candidates in COMMON_BROWSERS:
        path = next((item for item in candidates if Path(item).exists()), "")
        if path:
            found.append({"key": key, "name": name, "path": path})
    return found


def browser_settings() -> dict:
    ui = load_config().get("ui") or {}
    key = str(ui.get("browser_key") or "system")
    path = str(ui.get("browser_path") or "")
    options = detect_browsers()
    selected = next((item for item in options if item["key"] == key), None)
    if selected is None:
        return options[0]
    if path:
        selected = dict(selected, path=path)
    return selected


def save_browser_choice(key: str, path: str = "") -> None:
    cfg = load_config()
    ui = cfg.setdefault("ui", {})
    ui["browser_key"] = str(key or "system")
    ui["browser_path"] = str(path or "")
    save_config(cfg)


def last_boss_url() -> str:
    return str((load_config().get("ui") or {}).get("last_boss_url") or "").strip()


def remember_boss_url(url: str) -> None:
    url = str(url or "").strip()
    if not url:
        return
    cfg = load_config()
    cfg.setdefault("ui", {})["last_boss_url"] = url
    save_config(cfg)


def open_external_url(url: str) -> tuple[bool, str]:
    url = str(url or "").strip()
    if not url:
        return False, "链接为空"
    choice = browser_settings()
    path = str(choice.get("path") or "")
    if str(choice.get("key")) != "system" and path and Path(path).exists():
        try:
            subprocess.Popen([path, url], close_fds=True)
            return True, path
        except Exception as exc:
            return False, str(exc)
    try:
        opened = webbrowser.open(url)
        if opened:
            return True, "系统默认浏览器"
        os.startfile(url)  # type: ignore[attr-defined]
        return True, "Windows 默认程序"
    except Exception as exc:
        return False, str(exc)
