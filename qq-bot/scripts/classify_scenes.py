#!/usr/bin/env python3
"""
给 scenes.jsonl 里的每个小互动场景自动打标签。

三元分离（避免「情绪」和「关系」混进 tags）：
  - tags               : 这是什么互动（1~3 个，从固定 20 类里选）
  - relationship_stage : 宁宁与主要对话对象的关系（6 档）
  - emotion_state      : 宁宁此时的主导情绪（14 种）

输入 : corpus/scenes.jsonl（build_scenes.py 产出，跳过 is_h=true）
输出 : corpus/scenes_tagged.jsonl（原字段 + tags / relationship_stage / emotion_state）

用法 :
  python scripts/classify_scenes.py --limit 30 --batch 20    # 小批验证
  python scripts/classify_scenes.py                          # 全量（~3500 条，约 90 次调用，成本 <1 元）

依赖 : 复用 .env 里的 DEEPSEEK_API_KEY / BASE_URL / MODEL（qq-bot 虚拟环境里的 openai 库）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
QQ_BOT = os.path.join(ROOT, "qq-bot")
CORPUS = os.path.join(ROOT, "corpus")

# 确保能 import openai / dotenv（用 qq-bot 的 venv 跑时已在环境里）
sys.path.insert(0, os.path.join(QQ_BOT, ".venv", "Lib", "site-packages"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(QQ_BOT, ".env"))

from openai import OpenAI  # noqa: E402

TAGS = [
    "casual", "teasing", "embarrassed", "angry", "helping", "serious",
    "confused", "compliment", "denial", "friendly", "stranger",
    "close_friend", "romance_related", "school", "conflict", "comfort",
    "curious", "happy", "sad", "playful",
]
RELATIONSHIP_STAGES = [
    "stranger", "acquaintance", "friend", "close_friend", "romantic", "family",
]
EMOTIONS = [
    "happy", "embarrassed", "angry", "teasing", "calm", "flustered", "sad",
    "proud", "confused", "caring", "neutral", "excited", "anxious", "surprised",
]

SYSTEM_PROMPT = f"""你是《魔女的夜宴》角色行为分析师。下面给你若干段「小互动场景」，每段包含：
  - 前文：宁宁回复之前别人说了什么
  - 宁宁回复：宁宁本人说的话
  - 后续：宁宁说完之后别人怎么接

请判断每个场景中宁宁的互动类型、与对话对象的关系、以及她此刻的情绪。

输出要求：只返回一个 JSON 对象，键是场景编号（字符串），值是一个对象，形如：
{{"0": {{"tags": ["teasing", "embarrassed"], "relationship_stage": "friend", "emotion_state": "embarrassed"}}}}

约束：
  - tags 从下面 20 类里选 1~3 个（不要自创）：{", ".join(TAGS)}
  - relationship_stage 从下面 6 档选 1 个：{", ".join(RELATIONSHIP_STAGES)}
    判断依据是宁宁正在回复的那个主要对象（可能不只一个人，取最主要的）。
  - emotion_state 从下面 14 种选 1 个：{", ".join(EMOTIONS)}
  - 如果关系无法判断（比如前文只有旁白），relationship_stage 填 "acquaintance"。
  - 严格返回 JSON，不要输出任何解释文字。"""


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


def _render_batch(scenes: list[dict], offset: int) -> str:
    lines = []
    for i, s in enumerate(scenes):
        idx = offset + i
        lines.append(f"【场景 {idx}】")
        for c in s["context"]:
            lines.append(f"  - {c['speaker']}：{c['text']}")
        lines.append(f"  宁宁回复：{s['nene_response']}")
        for f in s["follow_up"]:
            lines.append(f"  - {f['speaker']}：{f['text']}")
    return "\n".join(lines)


def _tag_batch(client: OpenAI, scenes: list[dict], offset: int) -> dict[str, dict]:
    user = _render_batch(scenes, offset)
    resp = client.chat.completions.create(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        max_tokens=4000,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def _tag_scenes(client: OpenAI, scenes: list[dict], offset: int) -> dict[str, dict]:
    """批量打标签，带重试（LLM 偶发残缺 JSON）。"""
    for attempt in range(3):
        res = _tag_batch(client, scenes, offset)
        if len(res) >= len(scenes) * 0.8:  # 解析成功 >=80% 视为合格
            return res
        time.sleep(1.0 * (attempt + 1))
    return _tag_batch(client, scenes, offset)  # 最后一次尽力而为


def _tag_single(client: OpenAI, scene: dict, idx: int) -> dict:
    """单场景打标签（更可靠），失败返回空。"""
    res = _tag_batch(client, [scene], idx)
    return res.get(str(idx), {})


def _normalize(tag: dict) -> dict:
    """把 LLM 输出规整到固定词表，防止自创词污染下游。"""
    tags = [t for t in tag.get("tags", []) if t in TAGS][:3]
    stage = tag.get("relationship_stage", "acquaintance")
    if stage not in RELATIONSHIP_STAGES:
        stage = "acquaintance"
    emo = tag.get("emotion_state", "neutral")
    if emo not in EMOTIONS:
        emo = "neutral"
    return {"tags": tags, "relationship_stage": stage, "emotion_state": emo}


def main() -> int:
    ap = argparse.ArgumentParser(description="给宁宁互动场景打标签")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条（0=全量）")
    ap.add_argument("--batch", type=int, default=10, help="每次 LLM 调用处理的场景数")
    ap.add_argument("--in", dest="in_path", default=os.path.join(CORPUS, "scenes.jsonl"))
    ap.add_argument("--out", default=os.path.join(CORPUS, "scenes_tagged.jsonl"))
    args = ap.parse_args()

    scenes = [json.loads(l) for l in open(args.in_path, encoding="utf-8")]
    clean = [s for s in scenes if not s["is_h"]]
    if args.limit:
        clean = clean[: args.limit]
    total = len(clean)
    print(f"待标注场景 {total} 条，每批 {args.batch} 条，约 { -(-total // args.batch) } 次调用。")

    client = _client()
    tagged: list[dict] = []
    empty = 0
    for start in range(0, total, args.batch):
        batch = clean[start:start + args.batch]
        res = _tag_scenes(client, batch, start)
        ok = 0
        for i, s in enumerate(batch):
            idx = str(start + i)
            tag = _normalize(res.get(idx)) if idx in res else None
            if tag is None or not tag["tags"]:  # 该条没标上 → 单场景兜底重试
                tag = _normalize(_tag_single(client, s, start + i))
            if not tag["tags"]:
                empty += 1
            else:
                ok += 1
            s2 = dict(s)
            s2.update(tag)
            tagged.append(s2)
        print(f"  [{start + len(batch)}/{total}] 本批成功 {ok}/{len(batch)}")
        time.sleep(0.3)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for s in tagged:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"已写出 {len(tagged)} 条 → {args.out}（其中空标签 {empty} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
