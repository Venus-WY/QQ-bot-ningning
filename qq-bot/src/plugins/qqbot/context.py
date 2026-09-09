"""群聊上下文：每个群一个 deque，最多存 context_len 条。"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from .config import config


@dataclass
class Message:
    ts: float
    nickname: str
    user_id: int
    text: str


class GroupContext:
    def __init__(self, maxlen: int) -> None:
        self._messages: deque[Message] = deque(maxlen=maxlen)

    def add(self, msg: Message) -> None:
        self._messages.append(msg)

    def recent(self, n: int) -> list[Message]:
        return list(self._messages)[-n:]


_contexts: dict[int, GroupContext] = {}


def get_context(group_id: int) -> GroupContext:
    if group_id not in _contexts:
        _contexts[group_id] = GroupContext(maxlen=config.context_len)
    return _contexts[group_id]


def add_message(group_id: int, nickname: str, user_id: int, text: str) -> None:
    get_context(group_id).add(
        Message(ts=time.time(), nickname=nickname, user_id=user_id, text=text)
    )


# 两条相邻消息间隔超过此秒数，视为话题可能已切换（在上下文里插入分界标记）
TOPIC_GAP_SECONDS = 300


def format_recent(group_id: int, n: int | None = None) -> str:
    msgs = get_context(group_id).recent(n or config.context_len)
    lines: list[str] = []
    prev_ts: float | None = None
    for m in msgs:
        if prev_ts is not None and m.ts - prev_ts > TOPIC_GAP_SECONDS:
            lines.append("── 话题可能已切换 ──")
        lines.append(
            f"[{time.strftime('%H:%M', time.localtime(m.ts))}] {m.nickname}：{m.text}"
        )
        prev_ts = m.ts
    return "\n".join(lines)
