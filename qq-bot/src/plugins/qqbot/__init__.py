"""QQ 群「AI 群友」主处理器。

职责：收群消息 → 记录上下文 → 判断是否回复（@必回 / 主动插话）→ 调大模型 → 发送。
"""
from __future__ import annotations

import time
from typing import Any

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent

from .config import config
from .context import add_message, format_recent, get_context
from .llm import chat
from .persona import build_system_prompt
from .planner import should_bubble, should_speak
from . import memory
from . import distilled_persona
from . import knowledge

# 专业领域关键词：命中即视为「专业问题」，回复放宽字数上限并追求详细准确
TECH_KEYWORDS = (
    "计算机", "编程", "代码", "算法", "数据结构", "操作系统", "编译", "网络协议",
    "数据库", "分布式", "并发", "线程", "进程", "内存", "缓存", "Python", "C++",
    "Java", "Linux", "控制", "PID", "反馈", "伺服", "电机", "自动化", "PLC",
    "传感器", "信号", "滤波", "卡尔曼", "软件工程", "架构", "设计模式", "重构",
    "测试", "微服务", "接口", "集成电路", "芯片", "FPGA", "Verilog", "VHDL",
    "版图", "半导体", "晶圆", "电路", "时序", "功耗", "寄存器", "总线", "机器视觉",
    "机械臂", "机器人", "机械设计", "机械结构", "动力学", "运动学", "嵌入式", "单片机",
    "复杂度", "排序", "搜索", "递归", "哈希", "二叉树", "图论", "动态规划", "贪心",
)


def _is_tech_question(text: str) -> bool:
    """判断群里最近聊天是否涉及专业领域技术问题。"""
    return any(k in text for k in TECH_KEYWORDS)

# 每个群最近一次「主动发言」的时间戳（@可绕过冷却）
_last_reply: dict[int, float] = {}
# 主动冒泡（持续话题插话）的独立冷却：比普通插话长，避免频繁刷存在感
_last_bubble: dict[int, float] = {}
# 对话接续窗口：bot 回复后这么长时间内，群友的追问视为「接续对话」，放宽冷却、提高接话欲望
CONVERSATION_WINDOW = 180  # 秒

group_chat = on_message(priority=10, block=False)


@group_chat.handle()
async def handle(bot: Bot, event: MessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        return
    if not config.enabled:
        return
    if event.group_id not in config.groups:
        return
    # 跳过机器人自己发出去的消息（避免自我触发 / 自我回复循环）
    if event.user_id == event.self_id:
        return

    text = event.get_plaintext().strip()
    nickname = event.sender.card or event.sender.nickname or str(event.user_id)

    # 无条件记录群聊（无论是否回复），让模型有上下文
    if text:
        add_message(event.group_id, nickname, event.user_id, text)
        # 长期记忆：记录每个群友的发言，积累熟悉度 / 好感度（不影响核心人格）
        if event.user_id != event.self_id:
            memory.on_user_message(event.user_id, nickname, text)

    # @我 或 回复我 → 必回
    if event.is_tome():
        await _reply(
            bot, event, trigger="mention",
            target_id=event.user_id, target_nickname=nickname,
        )
        return

    # 被点名（消息里提到机器人名字，即使没 @）→ 必回
    if text and config.name and config.name in text:
        await _reply(
            bot, event, trigger="named",
            target_id=event.user_id, target_nickname=nickname,
        )
        return

    # 非 @ 且没有文字（如纯图片/纯表情）→ 不主动插话
    if not text:
        return

    # 冷却：刚主动说过话就先歇着（但对话接续窗口内放宽，便于多轮追问）
    last = _last_reply.get(event.group_id, 0.0)
    elapsed = time.time() - last
    in_conversation = elapsed < CONVERSATION_WINDOW
    if elapsed < config.min_reply_interval and not in_conversation:
        return
    if elapsed < 3:
        # 3 秒内的极短冷却，防止连发刷屏
        return

    # 主动插话决策（对话接续时提高回复欲望）
    context_text = format_recent(event.group_id, config.judge_context_len)
    speak, relevance, reason = await should_speak(context_text, in_conversation=in_conversation)
    logger.info(
        f"[群{event.group_id}] 插话决策 speak={speak} relevance={relevance:.2f} reason={reason}"
    )
    if speak:
        target_id, target_nickname = _target_speaker(event)
        await _reply(
            bot, event, trigger="proactive",
            target_id=target_id, target_nickname=target_nickname,
        )
        return

    # 主动冒泡：群里持续几分钟聊同一主题时，找机会插一句（独立且更长的冷却）
    if config.bubble_interval > 0:
        await _maybe_bubble(bot, event)


def _target_speaker(event: GroupMessageEvent) -> tuple[int | None, str]:
    """确定「正在和谁说话」：取最近一条非机器人消息的发言者。"""
    for m in reversed(get_context(event.group_id).recent(config.judge_context_len)):
        if m.user_id != event.self_id:
            return m.user_id, m.nickname
    return None, ""


async def _maybe_bubble(bot: Bot, event: GroupMessageEvent) -> None:
    """群里持续几分钟聊同一主题时，主动冒泡插一句（独立于普通插话，间隔更长）。"""
    now = time.time()
    msgs = get_context(event.group_id).recent(config.context_len)
    recent = [m for m in msgs if now - m.ts <= config.bubble_window]
    speakers = {m.user_id for m in recent if m.user_id != event.self_id}
    # 便宜启发式：时间窗内够活跃且不止一个人在说，才值得去问大模型
    if len(recent) < config.bubble_min_msgs or len(speakers) < 2:
        return
    # 冒泡冷却：最多 bubble_interval 秒一次，避免频繁刷存在感
    if now - _last_bubble.get(event.group_id, 0.0) < config.bubble_interval:
        return
    _last_bubble[event.group_id] = now

    long_ctx = format_recent(event.group_id, config.context_len)
    bubble, relevance, reason = await should_bubble(long_ctx)
    logger.info(
        f"[群{event.group_id}] 冒泡决策 speak={bubble} relevance={relevance:.2f} reason={reason}"
    )
    if not bubble:
        return
    target_id, target_nickname = _target_speaker(event)
    await _reply(
        bot, event, trigger="bubble",
        target_id=target_id, target_nickname=target_nickname,
    )


async def _reply(
    bot: Bot,
    event: GroupMessageEvent,
    trigger: str,
    target_id: int | None = None,
    target_nickname: str = "",
) -> None:
    context_text = format_recent(event.group_id)

    # 核心人格（只读；hanxiao=蒸馏人格 / luna=旧占位）+ 记忆 + few-shot
    if config.persona_source == "hanxiao":
        system_content = distilled_persona.build_system_prompt(config)
    else:
        system_content = build_system_prompt(config)

    if target_id is not None:
        block = memory.get_speaker_block(target_id, target_nickname)
        if block:
            system_content += "\n\n" + block

    if config.persona_source == "hanxiao":
        fb = distilled_persona.build_fewshot_block(context_text)
        if fb:
            system_content += "\n\n" + fb

    if config.persona_source == "hanxiao":
        rel_hint = distilled_persona.build_relation_hint(context_text)
        if rel_hint:
            system_content += "\n\n" + rel_hint

    kb_hint = knowledge.search_knowledge(context_text)
    if kb_hint:
        system_content += "\n\n" + kb_hint

    is_tech = _is_tech_question(context_text)
    tech_note = (
        "这是一个专业领域的技术问题，请给出详细、精准、准确无误的说明，"
        "可以分点或分步骤展开，不要简短敷衍。"
        if is_tech
        else ""
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": (
                f"以下是 QQ 群最近聊天（按时间先后，可能包含多个话题）：\n\n{context_text}\n\n"
                "请注意：群聊话题会随时转移，最后几条消息反映的才是当前话题。"
                "请围绕当前（最新）话题回复，不要继续纠缠更早的、已经结束的话题。"
                + (f"\n{tech_note}" if tech_note else "")
                + "\n请以群成员身份自然地回复。"
            ),
        },
    ]

    # 专业问题放宽回复长度（给足 token 空间输出详细说明）
    max_tokens = 800 if is_tech else 256
    try:
        reply = await chat(messages, max_tokens=max_tokens)
    except Exception as exc:
        logger.error(f"调用大模型失败：{exc}")
        return

    if not reply:
        return

    try:
        await bot.send_group_msg(group_id=event.group_id, message=reply)
    except Exception as exc:
        logger.error(f"发送消息失败：{exc}")
        return

    # 记录自己刚说的话，保证后续上下文连贯
    add_message(event.group_id, config.name, event.self_id, reply)
    _last_reply[event.group_id] = time.time()
    logger.info(f"[群{event.group_id}] 已回复（trigger={trigger}）：{reply}")
