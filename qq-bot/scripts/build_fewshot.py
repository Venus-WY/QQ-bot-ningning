#!/usr/bin/env python3
"""
从 scenes_tagged.jsonl 选 200~500 组高质量 few-shot，附行为摘要。

每条形如：
  {tags, emotion_state, relationship_stage, context, nene_response, behavior_summary}

运行时按 tags 检索最相关 3~6 条，注入 prompt 作「宁宁在类似情境下会怎么反应」的范例。

行为摘要 behavior_summary 用 LLM 批量生成（概括「别人做了什么 → 宁宁怎么反应」），
单条失败回退到模板（tag→emotion 拼一个）。选样按主 tag 分层，保证 20 类标签都覆盖。

用法 :
  python scripts/build_fewshot.py --target 400            # 选 400 组（默认）
  python scripts/build_fewshot.py --target 40 --limit 400 # 小批验证
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # 复用 distill_persona 的加载/LLM 工具
import distill_persona as dp  # noqa: E402

from distill_persona import RNG, _ask_json, _clip, _client, load_scenes  # noqa: E402

# tag -> 对方动作（模板回退用）
_ACT = {
    "compliment": "被夸", "teasing": "被调侃", "embarrassed": "被戳破", "angry": "生气",
    "helping": "被求助", "serious": "谈正事", "confused": "没听懂", "denial": "被质疑",
    "friendly": "闲聊", "stranger": "陌生人搭话", "close_friend": "好友互动",
    "romance_related": "恋爱话题", "school": "学校日常", "conflict": "起冲突",
    "comfort": "安慰人", "curious": "好奇追问", "happy": "开心互动", "sad": "情绪低落",
    "playful": "开玩笑", "casual": "闲聊",
}
_EMO = {
    "embarrassed": "害羞", "angry": "生气", "happy": "开心", "sad": "低落",
    "confused": "困惑", "teasing": "调侃", "caring": "关心", "flustered": "慌乱",
    "surprised": "惊讶", "proud": "得意", "calm": "平静", "neutral": "平静",
    "excited": "兴奋", "anxious": "不安",
}


def _template_summary(s: dict) -> str:
    tag = s["tags"][0] if s["tags"] else "casual"
    emo = s.get("emotion_state", "neutral")
    return f"{_ACT.get(tag, tag)}→{_EMO.get(emo, emo)}地回应"


def _compact_context(s: dict) -> str:
    return " ".join(f"{c['speaker']}：{c['text']}" for c in s["context"][-3:])


def select_fewshot(scenes: list[dict], target: int) -> list[dict]:
    """按主 tag 分层选样，保证覆盖，再补足到 target。"""
    pool = [s for s in scenes if s.get("context") and len(s["nene_response"]) >= 4]

    by_tag: dict[str, list[dict]] = collections.defaultdict(list)
    for s in pool:
        tag = s["tags"][0] if s["tags"] else "casual"
        by_tag[tag].append(s)

    per_tag = max(3, target // max(1, len(by_tag)))
    picked: list[dict] = []
    picked_ids: set[str] = set()
    for tag, lst in sorted(by_tag.items(), key=lambda kv: -len(kv[1])):
        for s in RNG.sample(lst, min(per_tag, len(lst))):
            picked.append(s)
            picked_ids.add(s["_id"])

    if len(picked) < target:
        rest = [s for s in pool if s["_id"] not in picked_ids]
        picked.extend(RNG.sample(rest, min(target - len(picked), len(rest))))
    return picked


def summarize(client, scenes: list[dict], batch: int) -> dict[str, str]:
    """批量生成 behavior_summary，返回 {_id: 摘要}。"""
    out: dict[str, str] = {}
    system = (
        "你是《魔女的夜宴》角色分析师。给每个场景写一句行为摘要，"
        "概括「别人做了什么 → 宁宁怎么反应」，用 → 连接因果，控制在 20 字内。\n"
        "只返回 JSON，键是场景编号（字符串），值是一句摘要。"
    )
    for start in range(0, len(scenes), batch):
        chunk = scenes[start:start + batch]
        lines = []
        for i, s in enumerate(chunk):
            idx = start + i
            ctx = " ".join(f"{c['speaker']}：{_clip(c['text'], 24)}" for c in s["context"][-3:])
            lines.append(f"【{idx}】{ctx} → 宁宁：{_clip(s['nene_response'], 36)}")
        data = _ask_json(client, system, "\n".join(lines), max_tokens=2000)
        for i, s in enumerate(chunk):
            idx = start + i
            summary = str(data.get(str(idx), "")).strip()
            out[s["_id"]] = summary or _template_summary(s)
        time.sleep(0.3)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="构建宁宁 few-shot 库")
    ap.add_argument("--target", type=int, default=400, help="few-shot 数量（200~500 建议）")
    ap.add_argument("--batch", type=int, default=30, help="摘要生成的批量大小")
    ap.add_argument("--limit", type=int, default=0, help="只用前 N 条验证（0=全量）")
    ap.add_argument("--no-summary", action="store_true", help="跳过 LLM 摘要，全用模板")
    ap.add_argument("--in", dest="in_path", default=os.path.join(dp.CORPUS, "scenes_tagged.jsonl"))
    ap.add_argument("--out", default=os.path.join(dp.CORPUS, "fewshot.jsonl"))
    args = ap.parse_args()

    scenes = load_scenes(args.in_path)
    if args.limit:
        scenes = scenes[: args.limit]

    picked = select_fewshot(scenes, args.target)
    print(f"从 {len(scenes)} 条里选出 {len(picked)} 组 few-shot。")

    if args.no_summary:
        summaries = {}
    else:
        summaries = summarize(_client(), picked, args.batch)
        missing = sum(1 for s in picked if s["_id"] not in summaries)
        print(f"行为摘要：LLM 生成 {len(summaries)} 条，缺 {missing} 条（用模板回退）。")

    with open(args.out, "w", encoding="utf-8") as f:
        for s in picked:
            entry = {
                "tags": s["tags"],
                "emotion_state": s.get("emotion_state", "neutral"),
                "relationship_stage": s.get("relationship_stage", "friend"),
                "context": _compact_context(s),
                "nene_response": s["nene_response"],
                "behavior_summary": summaries.get(s["_id"], _template_summary(s)),
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    dist = collections.Counter(s["tags"][0] for s in picked if s["tags"])
    print(f"已写出 {len(picked)} 条 → {args.out}")
    print("主 tag 覆盖：", dict(sorted(dist.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
