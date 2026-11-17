# -*- coding: utf-8 -*-
"""界面共享上下文：配置 + LLM 客户端工厂（界面不直接碰网络细节）。"""
from __future__ import annotations

from core.config import api_config, load_config
from core.llm import LLMClient


class AppContext:
    def __init__(self):
        self.cfg = load_config()

    def reload(self) -> None:
        self.cfg = load_config()

    def llm(self) -> LLMClient:
        return LLMClient(api_config(self.cfg))

    def model_name(self) -> str:
        return api_config(self.cfg).get("model") or ""

    def language(self) -> str:
        return (self.cfg.get("resume") or {}).get("output_language") or "中文"

    def import_marks_unconfirmed(self) -> bool:
        return bool((self.cfg.get("import") or {}).get("mark_unconfirmed", True))
