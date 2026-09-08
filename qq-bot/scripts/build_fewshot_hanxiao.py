#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从韩萧 spoken 语料选 400 组 few-shot，附行为摘要，覆盖 corpus/fewshot.jsonl。

每条形如：
  {tags, emotion_state, relationship_stage, context, response, behavior_summary}

行为摘要 behavior_summary 用 LLM 批量生成（概括「前文 → 韩萧怎么反应」），
失败回退到模板。选样按章节分层，保证覆盖全书不同时期。

用法 :
  python scripts/build_fewshot_hanxiao.py --target 400
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CORPUS = os.path.join(ROOT, "corpus")

sys.path.insert(0, HERE)
import distill_hanxiao as dh  # noqa: E402
from distill_hanxiao import RNG, _ask_json, _clip, _client, load_lines  # noqa: E402


def _template_summary(s: dict) -> str:
    tag = "回应"
    if s["type"] == "inner":
        return "韩萧内心盘算"
    return f"韩萧{tag}"


def _compact_context(s: dict) -> str:
    return (s.get("ctx_before", "") or "").strip()


def _guess_tags(s: dict) -> list[str]:
    """简单关键词给 tag，供检索（不求精确）。"""
    text = s["text"] + s.get("ctx_before", "")
    tags = []
    if any(k in text for k in ("钱", "交易", "买", "卖", "报酬", "信用点", "资源")):
        tags.append("trade")
    if any(k in text for k in ("打", "杀", "敌", "威胁", "战", "枪", "炮", "血")):
        tags.append("conflict")
    if any(k in text for k in ("机械", "装备", "机甲", "制造", "武器", "零件")):
        tags.append("tech")
    if any(k in text for k in ("计划", "布局", "算计", "策略", "情报")):
        tags.append("strategy")
    if any(k in text for k in ("?", "？", "吗", "呢")):
        tags.append("question")
    if not tags:
        tags.append("casual")
    return tags


def select_fewshot(lines: list[dict], target: int) -> list[dict]:
    spoken = [s for s in lines if s["type"] == "spoken" and len(s["text"]) >= 4]
    # 按章节分层
    by_ch: dict[str, list[dict]] = collections.defaultdict(list)
    for s in spoken:
        by_ch[s.get("chapter", "?")].append(s)
    per = max(1, target // max(1, len(by_ch)))
    picked: list[dict] = []
    for ch, lst in sorted(by_ch.items(), key=lambda kv: -len(kv[1])):
        picked.extend(RNG.sample(lst, min(per, len(lst))))
    if len(picked) > target:
        picked = RNG.sample(picked, target)
    return picked


def summarize(client, picked: list[dict], batch: int) -> dict[str, str]:
    out: dict[str, str] = {}
    system = (
        "你是小说《超神机械师》的角色分析师。给每条对白写一句行为摘要，"
        "概括「前文/情境 → 韩萧怎么回应」，用 → 连接因果，控制在 20 字内，"
        "突出韩萧的风格（冷静/毒舌/算计/装逼）。\n"
        "只返回 JSON，键是场景编号（字符串），值是一句摘要。"
    )
    for start in range(0, len(picked), batch):
        chunk = picked[start:start + batch]
        lines_ = []
        for i, s in enumerate(chunk):
            idx = start + i
            ctx = _clip(s.get("ctx_before", "") or "（无前文）", 30)
            lines_.append(f"【{idx}】{ctx} → 韩萧：{_clip(s['text'], 40)}")
        data = _ask_json(client, system, "\n".join(lines_), max_tokens=2500)
        for i, s in enumerate(chunk):
            idx = start + i
            summary = str(data.get(str(idx), "")).strip()
            out[s["_id"]] = summary or _template_summary(s)
        time.sleep(0.3)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="构建韩萧 few-shot 库")
    ap.add_argument("--target", type=int, default=400)
    ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-summary", action="store_true")
    ap.add_argument("--in", dest="in_path", default=os.path.join(CORPUS, "hanxiao_lines.jsonl"))
    ap.add_argument("--out", default=os.path.join(CORPUS, "fewshot.jsonl"))
    args = ap.parse_args()

    lines = load_lines(args.in_path)
    if args.limit:
        lines = lines[: args.limit]

    picked = select_fewshot(lines, args.target)
    print(f"从 {len(lines)} 条里选出 {len(picked)} 组 few-shot。")

    if args.no_summary:
        summaries = {}
    else:
        summaries = summarize(_client(), picked, args.batch)
        print(f"行为摘要：LLM 生成 {len(summaries)} 条。")

    with open(args.out, "w", encoding="utf-8") as f:
        for s in picked:
            entry = {
                "tags": _guess_tags(s),
                "emotion_state": "neutral",
                "relationship_stage": "friend",
                "context": _compact_context(s),
                "response": s["text"],
                "behavior_summary": summaries.get(s["_id"], _template_summary(s)),
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    dist = collections.Counter(t for s in picked for t in _guess_tags(s))
    print(f"已写出 {len(picked)} 条 → {args.out}")
    print("tag 覆盖：", dict(sorted(dist.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
