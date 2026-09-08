"""DeepSeek（OpenAI 兼容）客户端封装：生成回复 + 插话判断。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx2 as httpx
from openai import AsyncOpenAI

from .config import config

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        # trust_env=False：绕过 Windows 系统代理（127.0.0.1:7897），直连国内 DeepSeek。
        _client = AsyncOpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            http_client=httpx.AsyncClient(trust_env=False, timeout=60.0),
        )
    return _client


async def chat(messages: list[dict[str, Any]], max_tokens: int = 256) -> str:
    """生成一句群聊回复。"""
    resp = await _get_client().chat.completions.create(
        model=config.llm_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.9,
    )
    return (resp.choices[0].message.content or "").strip()


async def chat_json(
    messages: list[dict[str, Any]],
    max_tokens: int = 400,
    temperature: float = 0.3,
) -> dict:
    """让模型输出 JSON 对象并解析，失败返回空 dict（记忆提取等用）。"""
    resp = await _get_client().chat.completions.create(
        model=config.llm_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


@dataclass
class SpeakDecision:
    speak: bool
    relevance: float
    reason: str


async def judge(messages: list[dict[str, Any]]) -> SpeakDecision:
    """让模型判断「是否该插话」，输出 JSON。"""
    resp = await _get_client().chat.completions.create(
        model=config.llm_model,
        messages=messages,
        max_tokens=200,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return SpeakDecision(speak=False, relevance=0.0, reason="解析失败，默认沉默")
    return SpeakDecision(
        speak=bool(data.get("speak", False)),
        relevance=float(data.get("relevance", 0.0)),
        reason=str(data.get("reason", "")),
    )
