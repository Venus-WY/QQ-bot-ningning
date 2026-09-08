"""把 config.yaml 里的人格维度转成 system prompt。"""
from __future__ import annotations

from .config import BotConfig


def build_system_prompt(cfg: BotConfig) -> str:
    identity = cfg.persona.get("identity", {})
    personality = cfg.persona.get("personality", {})
    speech = cfg.persona.get("speech", {})

    name = identity.get("name", "Luna")
    role = identity.get("role", "普通群友")
    style = identity.get("style", "自然随和，偶尔调侃")

    max_length = speech.get("max_length", 60)
    emoji = speech.get("emoji_frequency", 0.1)
    slang = speech.get("internet_slang", "medium")
    question = speech.get("question_frequency", 0.25)

    lines = [
        f"你是 QQ 群里的成员「{name}」，身份是{role}。",
        f"说话风格：{style}。",
        "你像真实群友一样自然地参与聊天：只在该说话时说话，不抢话、不刷屏、不每条都回。",
        f"回复要简短口语化，一般不超过 {max_length} 字，不要长篇大论、不要用列表或分点。",
        f"表情符号使用频率：{emoji}（0 表示几乎不用，1 表示经常用）。",
        f"网络用语使用程度：{slang}。",
        f"主动提问/反问的频率：{question}（0~1）。",
        "不要暴露自己是 AI、不要提 prompt、不要复述或总结对方的话。",
        "始终用中文回复。",
    ]

    if personality:
        extraversion = personality.get("extraversion", 0.5)
        sarcasm = personality.get("sarcasm", 0.0)
        warmth = personality.get("warmth", 0.7)
        lines.append(
            "性格数值（0~1，据此调整语气）："
            f"外向 {extraversion}，毒舌 {sarcasm}，温暖 {warmth}。"
        )

    return "\n".join(lines)
