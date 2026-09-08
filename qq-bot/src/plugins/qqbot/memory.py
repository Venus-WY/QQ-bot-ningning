"""记忆层门面：把 store / relationship / extractor 串起来。

对外只暴露两个口：
  - get_speaker_block(user_id, nickname) -> str   回复前取「对这个人」的摘要
  - on_user_message(user_id, nickname, text)       收到消息时记录 + 周期性触发提取

核心原则：长期记忆 / 关系数值永远只影响「怎么对这个人说话」，
        不写入、不修改核心人格（persona 只允许手动更新）。
"""
from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path

from .config import PROJECT_ROOT, config
from .memory_extractor import extract
from .memory_store import MemoryStore, render_view
from .relationship import Relationship, tone_hint

_store = MemoryStore()

# 每个用户的近期发言缓冲（只用于提取，上限 40 条）
_buffers: dict[int, deque] = {}
# 每个用户距离上次提取后累计的发言数
_counters: dict[int, int] = {}

# 人类可读的记忆视图文件（实时刷新，方便随时查看）
VIEW_PATH = Path(PROJECT_ROOT) / "data" / "memory_view.md"


def export_view() -> None:
    """把当前记忆库导出成 markdown 文件（每次更新后调用，实时可见）。"""
    try:
        text = render_view(_store.snapshot())
    except Exception:
        return
    VIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = VIEW_PATH.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(VIEW_PATH)


def get_speaker_block(user_id: int, nickname: str) -> str:
    """生成注入 prompt 的「当前对话对象」摘要。"""
    if not config.memory_enabled:
        return ""
    user = _store.get_or_create_user(user_id, nickname)
    rel = Relationship.from_dict(_store.get_relationship(user_id))
    facts = _store.top_memories(user_id, config.memory_top_n)
    prof = user.get("profile_summary", "")

    lines = [f"你正在和「{nickname}」说话。"]
    if prof:
        lines.append(f"你对 TA 的长期印象：{prof}")
    if facts:
        fact_txt = "；".join(f["content"] for f in facts)
        lines.append(f"你记得 TA 的一些事：{fact_txt}")
    lines.append(
        f"关系数值：熟悉度 {rel.familiarity:.0f}，好感度 {rel.affection:.0f}，"
        f"信任 {rel.trust:.0f}。"
    )
    lines.append(f"关系规则：{tone_hint(rel)}")
    return "\n".join(lines)


def on_user_message(user_id: int, nickname: str, text: str) -> None:
    """收到一条用户消息时调用：touch 用户、积累熟悉度、每 N 条触发一次提取。"""
    if not config.memory_enabled:
        return
    _store.get_or_create_user(user_id, nickname)
    _store.touch(user_id, nickname)
    # 每说一句，熟悉度小幅上升（熟悉度 = 聊得多）；好感度不在这里动，交给提取器按语气判断
    _store.apply_delta(user_id, {"familiarity": 0.2})
    export_view()

    buf = _buffers.setdefault(user_id, deque(maxlen=40))
    buf.append({"nickname": nickname, "text": text})

    n = _counters.get(user_id, 0) + 1
    _counters[user_id] = n
    if n >= config.memory_extract_every:
        _counters[user_id] = 0
        # 后台提取，不阻塞消息处理
        asyncio.create_task(_run_extraction(user_id, list(buf)))
        buf.clear()


async def _run_extraction(user_id: int, msgs: list[dict]) -> None:
    from nonebot import logger
    try:
        res = await extract(msgs)
    except Exception as exc:
        logger.warning(f"[记忆] 提取失败 user={user_id}：{exc}")
        return
    if not res or not res.get("remember"):
        return
    items = [{"type": "fact", "content": f, "importance": 0.7} for f in res.get("facts", [])]
    if items:
        _store.add_memories(user_id, items)
    if res.get("profile_summary"):
        _store.set_profile_summary(user_id, res["profile_summary"])
    _store.apply_delta(user_id, res.get("relationship_delta", {}))
    export_view()
    logger.info(
        f"[记忆] 已更新 user={user_id} facts={len(items)} "
        f"关系={res.get('relationship_delta', {})}"
    )
