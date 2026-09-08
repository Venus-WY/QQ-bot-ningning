"""对外插件接口（非插件：目录以 `_` 开头，NoneBot2 会自动跳过、不加载为插件）。

朋友写功能插件时，从这里复用现成的东西：

    from src.plugins._shared import config, group_allowed, chat, chat_json

- config         共享配置（群白名单 / 模型 / key）
- group_allowed  群白名单校验
- chat / chat_json  共享 DeepSeek 客户端（已处理代理，别自己 new 一个）
"""
from .config import config, group_allowed
from .llm import chat, chat_json
from .image_pool import (
    get_image_by_character,
    get_image_by_series,
    get_image_by_tag,
    get_random_image,
)

__all__ = [
    "config",
    "group_allowed",
    "chat",
    "chat_json",
    "get_random_image",
    "get_image_by_character",
    "get_image_by_series",
    "get_image_by_tag",
]
