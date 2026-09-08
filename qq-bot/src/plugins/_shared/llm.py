"""共享 DeepSeek 客户端（OpenAI 兼容，异步）。

带 trust_env=False：绕过 Windows 系统代理（127.0.0.1:7897），直连国内 DeepSeek。
朋友插件用 `from src.plugins._shared import chat, chat_json` 复用同一个客户端。
"""
from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
from openai import AsyncOpenAI

from .config import config

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            http_client=httpx.AsyncClient(trust_env=False, timeout=60.0),
        )
    return _client


async def chat(messages: list[dict[str, Any]], max_tokens: int = 256) -> str:
    """生成一段文本。"""
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
    """让模型输出 JSON 对象并解析，失败返回空 dict。"""
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
