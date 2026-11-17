# -*- coding: utf-8 -*-
"""LLM 适配层：默认 DeepSeek（OpenAI 兼容协议），换模型/服务商只改 config.json。

对外只暴露两件事：
- complete_text(): 要一段文字
- complete_json(): 要一个 JSON 对象（容错解析 + 必要字段校验 + 温度阶梯重试 + 错误回灌）

每次调用都写日志（耗时 / token / 字符数），失败时抛出带中文说明的 LLMError。
"""
from __future__ import annotations

import json
import re
import time

from core.applog import get_logger

log = get_logger("llm")

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - 环境缺库时给出明确提示
    OpenAI = None


class LLMError(Exception):
    """调用大模型失败（网络 / Key / 返回格式等）。"""


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> dict:
    """从模型回复里尽力抠出一个 JSON 对象。"""
    if not text or not text.strip():
        raise LLMError("模型返回为空")
    raw = text.strip()
    m = _FENCE_RE.search(raw)
    if m:
        raw = m.group(1).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(raw)):
            ch = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(raw[start : i + 1])
                        if isinstance(data, dict):
                            return data
                    except json.JSONDecodeError:
                        pass
                    break
        start = raw.find("{", start + 1)
    raise LLMError("模型返回的内容不是合法 JSON")


class LLMClient:
    """一次调用 = 一次对话；不做业务判断，业务判断在 generate/guard 里。"""

    def __init__(self, api_cfg: dict):
        self.cfg = dict(api_cfg or {})
        self.model = self.cfg.get("model") or "deepseek-chat"
        self._client = None

    @property
    def api_key(self) -> str:
        return (self.cfg.get("api_key") or "").strip()

    def ensure_ready(self) -> None:
        if OpenAI is None:
            raise LLMError("未安装 openai 库，请执行：pip install openai")
        if not self.api_key:
            raise LLMError("尚未填写 API Key，请在「设置」里填写")
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.cfg.get("base_url") or None,
                timeout=self.cfg.get("timeout") or 120,
            )

    # ------------------------------------------------------------ 文本
    def complete_text(
        self, system: str, user: str, temperature=None, max_tokens=None
    ) -> str:
        self.ensure_ready()
        temp = self.cfg.get("temperature", 0.3) if temperature is None else temperature
        tokens = max_tokens or self.cfg.get("max_tokens") or 4096
        t0 = time.time()
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temp,
                max_tokens=tokens,
            )
        except Exception as exc:
            log.error("LLM 调用失败：%s", exc)
            raise LLMError("调用模型失败：%s" % exc) from exc
        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        log.info(
            "LLM ok model=%s temp=%s 耗时=%.1fs 输入字符=%d 输出字符=%d tokens=%s",
            self.model,
            temp,
            time.time() - t0,
            len(system) + len(user),
            len(text),
            getattr(usage, "total_tokens", "-"),
        )
        return text

    # ------------------------------------------------------------ JSON
    def complete_json(
        self,
        system: str,
        user: str,
        required_keys=None,
        max_tokens=None,
        temperature=None,
        attempts: int = 3,
        retry_hint: str = "",
    ) -> dict:
        last_err = None
        hint = retry_hint
        ladder = (0.1, 0.3, 0.5, 0.7)
        for i in range(max(1, attempts)):
            temp = ladder[min(i, len(ladder) - 1)] if temperature is None else temperature
            prompt = user + (("\n\n" + hint) if hint else "")
            try:
                text = self.complete_text(system, prompt, temperature=temp, max_tokens=max_tokens)
                data = extract_json(text)
                missing = [k for k in (required_keys or []) if k not in data]
                if missing:
                    raise LLMError("缺少必要字段：%s" % "、".join(missing))
                return data
            except LLMError as exc:
                last_err = exc
                hint = (
                    "上一次输出不合格（%s）。请只输出一个完整、合法的 JSON 对象，"
                    "不要任何解释文字、不要 Markdown 代码块。" % exc
                )
                log.warning("complete_json 第 %d 次失败：%s", i + 1, exc)
        raise LLMError("多次尝试后仍未拿到可用 JSON：%s" % last_err)

    # ------------------------------------------------------------ 自检
    def test_connection(self) -> str:
        return self.complete_text(
            "你是一个测试助手。", "只回复两个字：可用", temperature=0, max_tokens=20
        )
