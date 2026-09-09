"""世界观知识库：加载《超神机械师》名词知识库，群聊提到相关概念时注入提示。

数据源：corpus/knowledge.yaml（地点/人物/装备/事件/技能/知识 六类名词）。
运行时只读，按需检索（群聊文本里命中哪个名词就注入哪个，不整库塞进 prompt）。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_PATH = PROJECT_ROOT.parent / "corpus" / "knowledge.yaml"


@lru_cache(maxsize=1)
def load_knowledge() -> dict[str, list[str]]:
    with open(KNOWLEDGE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def search_knowledge(text: str, max_hits: int = 6) -> str:
    """检测群聊文本里出现的世界观名词，返回注入提示（无命中返回空串）。"""
    knowledge = load_knowledge()
    if not text or not knowledge:
        return ""

    hits: list[tuple[str, str]] = []
    # 先收集所有命中，再按名词长度降序（长词更具体，优先保留）
    for category, names in knowledge.items():
        for name in names:
            if len(name) >= 2 and name in text:
                hits.append((category, name))

    if not hits:
        return ""

    # 去重（同一词可能归到多类）+ 按长度降序，长词命中后跳过其子串
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for cat, name in sorted(hits, key=lambda x: -len(x[1])):
        if name in seen:
            continue
        # 若该词是已命中长词的子串，跳过（避免「海蓝星」命中后又冒出「蓝星」「海蓝」）
        if any(name in longer for _, longer in unique):
            continue
        seen.add(name)
        unique.append((cat, name))
    unique = unique[:max_hits]

    parts = "、".join(f"「{name}」（{cat}）" for cat, name in unique)
    return (
        f"群聊里提到了你所在世界观的概念：{parts}。"
        f"你对这些很熟悉，可以自然地接着聊，别表现得像没听说过。"
    )
