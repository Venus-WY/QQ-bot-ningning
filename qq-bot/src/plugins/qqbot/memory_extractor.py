"""记忆提取器：周期性让小模型从某人的近期发言里提炼长期事实 + 关系增减。

只在积累够 N 条后调用一次，避免把「哈哈哈」「今天吃啥」这类垃圾塞进长期记忆。
输出 JSON：{ remember, facts[], profile_summary, relationship_delta{...} }
"""
from __future__ import annotations

from .llm import chat_json

_SYSTEM = (
    "你是群聊记忆助手。下面给你某个群友最近在群里说的一些话，请判断有没有值得长期记住的信息。\n"
    "要求：\n"
    "  - 只记住稳定/有信息量的事实：专业、兴趣、身份、常玩的游戏、说话习惯、近期大事等。\n"
    "  - 忽略寒暄、表情、「哈哈哈」、无意义闲聊。\n"
    "  - relationship_delta 用来更新你（AI）对 TA 的关系数值，每项范围 -5 ~ +5，"
    "不要凭空给分，只根据 TA 这轮表现：友善/帮忙/真诚可小幅加好感或信任；"
    "辱骂/恶意攻击减好感；纯闲聊只加熟悉度。\n"
    "  - 只返回 JSON，格式："
    "{\"remember\": true/false, \"facts\": [\"...\"], \"profile_summary\": \"一句话人物画像\", "
    "\"relationship_delta\": {\"familiarity\": 0, \"affection\": 0, \"trust\": 0, \"teasing_tolerance\": 0}}\n"
    "不要输出 JSON 以外的内容。"
)

_DELTA_KEYS = ("familiarity", "affection", "trust", "teasing_tolerance")


def _render_user(msgs: list[dict]) -> str:
    return "\n".join(f"- {m['nickname']}：{m['text']}" for m in msgs)


async def extract(msgs: list[dict]) -> dict:
    """msgs: [{nickname, text}, ...] 同一用户近期发言。返回规整后的 dict。"""
    if not msgs:
        return {}
    user = _render_user(msgs)
    data = await chat_json(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"以下是 TA 最近的发言：\n\n{user}\n\n请判断，输出 JSON。"},
        ],
        max_tokens=600,
        temperature=0.2,
    )
    return _normalize(data)


def _normalize(data: dict) -> dict:
    facts = [f.strip() for f in data.get("facts", []) if isinstance(f, str) and f.strip()]
    delta = data.get("relationship_delta", {}) or {}

    def bounded(k: str) -> float:
        try:
            return max(-5.0, min(5.0, float(delta.get(k, 0.0))))
        except (TypeError, ValueError):
            return 0.0

    return {
        "remember": bool(data.get("remember", bool(facts))),
        "facts": facts,
        "profile_summary": str(data.get("profile_summary", "")).strip(),
        "relationship_delta": {k: bounded(k) for k in _DELTA_KEYS},
    }
