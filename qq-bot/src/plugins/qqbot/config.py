"""读取 config.yaml 与 .env，产出统一的 BotConfig。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from nonebot import logger

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# 显式加载 .env：NoneBot 会加载它自己那部分配置，这里保证我们的 key 也进 os.environ
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class BotConfig:
    groups: list[int]
    min_reply_interval: float
    context_len: int
    judge_context_len: int
    bubble_interval: float
    bubble_window: float
    bubble_min_msgs: int
    persona: dict[str, Any]
    persona_source: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    memory_enabled: bool
    memory_extract_every: int
    memory_top_n: int

    @property
    def enabled(self) -> bool:
        return bool(self.llm_api_key and self.groups)

    @property
    def name(self) -> str:
        return self.persona.get("identity", {}).get("name", "Luna")


def load_config() -> BotConfig:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    behavior = raw.get("behavior", {})
    memory = raw.get("memory", {})
    return BotConfig(
        groups=[int(g) for g in raw.get("groups", [])],
        min_reply_interval=float(behavior.get("min_reply_interval", 30)),
        context_len=int(behavior.get("context_len", 30)),
        judge_context_len=int(behavior.get("judge_context_len", 20)),
        bubble_interval=float(behavior.get("bubble_interval", 300)),
        bubble_window=float(behavior.get("bubble_window", 180)),
        bubble_min_msgs=int(behavior.get("bubble_min_msgs", 6)),
        persona=raw.get("persona", {}),
        persona_source=str(raw.get("persona", {}).get("source", "luna")),
        llm_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        llm_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        llm_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        memory_enabled=bool(memory.get("enabled", True)),
        memory_extract_every=int(memory.get("extract_every", 15)),
        memory_top_n=int(memory.get("top_n", 8)),
    )


config = load_config()

if not config.enabled:
    logger.warning(
        "QQ 群机器人未启用：请在 .env 填入 DEEPSEEK_API_KEY，"
        "并在 config.yaml 的 groups 里填入群号。"
    )
else:
    logger.info(f"已加载配置：groups={config.groups} model={config.llm_model}")
