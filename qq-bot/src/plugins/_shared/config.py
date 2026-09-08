"""共享配置：读取同一份 config.yaml + .env。

与 qqbot 插件内的 config 相互独立（不 import qqbot），避免跨插件 import
触发 NoneBot2 的 "not loaded as a plugin" 问题。朋友插件只 import 本文件。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

# 本文件在 qq-bot/src/plugins/_shared/ 下，往上 3 级 = qq-bot
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class SharedConfig:
    groups: list[int]
    name: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str


def _load() -> SharedConfig:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    persona = raw.get("persona", {})
    return SharedConfig(
        groups=[int(g) for g in raw.get("groups", [])],
        name=str(persona.get("identity", {}).get("name", "Luna")),
        llm_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        llm_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        llm_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
    )


config = _load()


def group_allowed(group_id: int) -> bool:
    """群白名单校验：只有在 config.yaml 的 groups 里的群才响应。"""
    return group_id in config.groups
