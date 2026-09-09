#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清洗知识库 + 生成描述（LLM 批处理）。

对 corpus/knowledge.yaml 里的每个名词：
  1. 判断是否是《超神机械师》世界观专有名词（通用词如「通讯」「和平」→ 剔除）
  2. 给专有名词写一句简短描述（20 字内）

输出：corpus/knowledge.yaml 重写为 {分类: {名词: 描述}} 格式。

用法 :
  python scripts/clean_and_describe.py [--batch 30] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
QQ_BOT = os.path.join(ROOT, "qq-bot")
CORPUS = os.path.join(ROOT, "corpus")
KNOWLEDGE_PATH = os.path.join(CORPUS, "knowledge.yaml")

sys.path.insert(0, os.path.join(QQ_BOT, ".venv", "Lib", "site-packages"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(QQ_BOT, ".env"))

from openai import OpenAI  # noqa: E402


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


def _ask_json(client, items: list[tuple[str, str]], batch_idx: int) -> dict:
    """一次处理一批名词，返回 {名词: {"special": bool, "desc": str}}。"""
    listing = "\n".join(f"{i}. [{cat}] {name}" for i, (cat, name) in enumerate(items))
    system = (
        "你是小说《超神机械师》的世界观整理助手。下面给你一批名词（已标注大类）。\n"
        "请逐条判断：\n"
        "  1. special：是否是该小说的世界观专有名词（地点/人物/装备/事件/技能/设定术语）。\n"
        "     通用日常词（如「通讯」「和平」「普通」「汇报」「聊天」「文明」这类泛词）→ false，要剔除。\n"
        "  2. desc：若是专有名词，写一句简短描述（15~25 字，说明它是什么）；若 special=false，desc 留空。\n"
        "只返回一个 JSON 对象，键是名词本身，值形如 {\"special\": true/false, \"desc\": \"...\"}。\n"
        "不要输出 JSON 以外的内容。"
    )
    user = "待处理名词：\n" + listing
    last = {}
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=3000,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or "{}"
            last = json.loads(content)
            if last:
                return last
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return last


def main() -> int:
    ap = argparse.ArgumentParser(description="清洗知识库并生成描述")
    ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个（0=全部）")
    args = ap.parse_args()

    data = yaml.safe_load(open(KNOWLEDGE_PATH, encoding="utf-8"))

    items: list[tuple[str, str]] = []
    for cat, names in data.items():
        for name in names:
            items.append((cat, name))

    if args.limit:
        items = items[: args.limit]

    client = _client()
    out: dict[str, dict[str, str]] = {}
    removed = 0

    for i in range(0, len(items), args.batch):
        chunk = items[i:i + args.batch]
        result = _ask_json(client, chunk, i // args.batch)
        for cat, name in chunk:
            r = result.get(name) or {}
            special = bool(r.get("special", False))
            desc = str(r.get("desc", "")).strip()
            if not special:
                removed += 1
                continue
            out.setdefault(cat, {})[name] = desc or f"《超神机械师》中的{cat}"
        print(f"  已处理 {min(i + args.batch, len(items))}/{len(items)}，累计剔除 {removed} 个", flush=True)
        time.sleep(0.3)

    # 写回
    with open(KNOWLEDGE_PATH, "w", encoding="utf-8") as f:
        f.write("# ===== 《超神机械师》世界观知识库 =====\n")
        f.write("# 格式：分类 -> {名词: 一句话描述}\n")
        f.write("# 由 scripts/clean_and_describe.py 用 LLM 清洗并生成描述。\n\n")
        for cat in ["地点", "人物", "装备", "事件", "技能", "知识"]:
            entries = out.get(cat, {})
            f.write(f"{cat}:\n")
            for name, desc in entries.items():
                f.write(f"  {name}: {desc}\n")
            f.write("\n")

    total = sum(len(v) for v in out.values())
    print(f"\n完成：剔除 {removed} 个通用名词，保留 {total} 个专有名词。")
    for cat in ["地点", "人物", "装备", "事件", "技能", "知识"]:
        print(f"  {cat}: {len(out.get(cat, {}))} 个")
    return 0


if __name__ == "__main__":
    exit(main())
