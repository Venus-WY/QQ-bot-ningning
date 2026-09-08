"""Speak Decision：判断「要不要插话」。"""
from __future__ import annotations

from .llm import judge


def _persona_hint() -> str:
    """宁宁插话倾向提示（未启用 nene 人格时为空）。"""
    try:
        from .config import config as _cfg
        if _cfg.persona_source == "nene":
            from . import nene_persona
            return nene_persona.should_speak_hint() + "\n"
    except Exception:
        pass
    return ""


async def should_speak(context_text: str) -> tuple[bool, float, str]:
    """返回 (是否回复, 相关性, 理由)。"""
    system = _persona_hint() + (
        "你是一个 QQ 群成员。根据最近聊天内容判断你是否应该加入对话。\n"
        "话题和你有关系、有人明确需要回应、或你真有想说的话时才参与；"
        "与你无关、也没必要插话时就保持沉默，不用为了活跃而硬接。\n"
        "只输出一个 JSON 对象，格式：{\"speak\": true或false, \"relevance\": 0到1的小数, "
        "\"reason\": \"一句话理由\"}，不要输出 JSON 以外的任何内容。"
    )
    user = f"以下是 QQ 群最近聊天：\n\n{context_text}\n\n请判断你是否应该插话，输出 JSON。"

    decision = await judge(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )

    # 直接信任模型的 speak 决定，不再叠加二次抽签（概率门会把本就偏谨慎的判断压得更安静）。
    # 频率控制交给 __init__.py 的冷却（min_reply_interval）。
    return decision.speak, decision.relevance, decision.reason


async def should_bubble(context_text: str) -> tuple[bool, float, str]:
    """判断「要不要主动冒泡」：群里持续几分钟聊一个话题时，是否插一句自己的看法。"""
    system = _persona_hint() + (
        "你是一个 QQ 群成员。群里最近几分钟在持续聊一个话题。\n"
        "群友持续聊日常话题（吃、玩、追番、天气、工作学习等）时，正常群成员会偶尔自然接一句，"
        "你也偶尔接一句就好，不必每次都冒泡；真有想接的话、或话题和你有关联时才说，"
        "话题你完全不了解、也没什么可说时就不硬接。\n"
        "只输出一个 JSON 对象，格式：{\"speak\": true或false, \"relevance\": 0到1的小数, "
        "\"reason\": \"一句话理由\"}，不要输出 JSON 以外的任何内容。"
    )
    user = (
        f"以下是 QQ 群最近几分钟的聊天：\n\n{context_text}\n\n"
        "请判断你是否要冒泡插一句，输出 JSON。"
    )
    decision = await judge(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    return decision.speak, decision.relevance, decision.reason
