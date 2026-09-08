#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《超神机械师》韩萧语料提取（高精度版）—— 从 txt 提取韩萧的对话与内心独白。

只认两种高置信结构，宁可漏不可错：
  1. 后置式：“内容”(,)?韩萧(动词/动作)    —— 引号后紧跟韩萧，引号内容必是韩萧的话
  2. 前置式：韩萧(修饰)+(说话/心理动词)[:：]“内容”  —— 韩萧后跟动词+冒号+引号

type 判定：动词含「暗/心/腹/默/思/想/忖/寻」→ inner（内心独白），否则 spoken。

输出 : corpus/hanxiao_lines.jsonl
  每条第 {text, type, verb, ctx_before, ctx_after, chapter}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_TXT = os.path.join(ROOT, "超神机械师 (齐佩甲).txt")
DEFAULT_OUT = os.path.join(ROOT, "corpus")

NAME = "韩萧"
LQ, RQ = "\u201c", "\u201d"

# 内心活动动词（→ inner）
INNER_MARK = ("暗", "心", "腹", "默", "思", "想", "忖", "寻", "念叨")
# 说话动词（→ spoken），用于前置式「韩萧X：」里 X 的合法性判断
SPOKEN_CORE = ("道", "说", "问", "答", "喊", "叫", "喝", "嚷", "骂", "叹", "笑",
               "开口", "补充", "解释", "反驳", "质问", "打趣", "安慰", "低语",
               "嘀咕", "回应", "冷笑", "冷哼", "吐槽", "调侃", "嗤笑", "哼")

BOUNDARY = "。！？!?…；;"


def _type_of(verb: str) -> str:
    if any(k in verb for k in INNER_MARK):
        return "inner"
    return "spoken"


def _is_speech_verb(verb: str) -> bool:
    """前置式里「韩萧X：」的 X 是否像说话/心理动词（排除纯动作）。"""
    if not verb:
        return False
    if any(k in verb for k in INNER_MARK):
        return True  # 暗道/心想/腹诽 等
    if any(k in verb for k in SPOKEN_CORE):
        return True  # 道/说/问/吐槽 等
    return False


def _ctx_before(line: str, pos: int, n: int = 100) -> str:
    """引号前的一段连续文本（不截句边界，尽量保留别人说的话/旁白作为前文）。"""
    return line[:pos].strip()[-n:]


def _ctx_after(line: str, pos: int, n: int = 60) -> str:
    return line[pos:].strip()[:n]


def extract(text: str) -> list[dict]:
    out: list[dict] = []
    chapter = "?"

    # 后置式：引号后紧跟（可带逗号）韩萧
    post_re = re.compile(rf"{LQ}([^{RQ}]{{2,200}}){RQ}\s*[，,]?\s*{NAME}\s*([\u4e00-\u9fff]{{1,5}})")
    # 前置式：韩萧 + 动词 + 冒号 + 引号
    pre_re = re.compile(rf"{NAME}\s*([\u4e00-\u9fff]{{1,8}}?)[:：]\s*{LQ}([^{RQ}]{{2,200}}){RQ}")

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^第[0-9零一二三四五六七八九十百千]+章", line)
        if m:
            chapter = line[:24]
            continue
        if NAME not in line or LQ not in line:
            continue

        used_spans: list[tuple[int, int]] = []

        # 1) 后置式
        for pm in post_re.finditer(line):
            s, e = pm.start(1), pm.end(1)
            inner = pm.group(1).strip()
            verb = pm.group(2)
            if any(s <= ps and pe <= e or ps <= s and e <= pe for ps, pe in used_spans):
                continue
            used_spans.append((s, e))
            out.append({
                "text": inner,
                "type": _type_of(verb),
                "verb": verb,
                "ctx_before": _ctx_before(line, pm.start()),
                "ctx_after": _ctx_after(line, pm.end()),
                "chapter": chapter,
            })

        # 2) 前置式
        for pm in pre_re.finditer(line):
            s, e = pm.start(2), pm.end(2)
            inner = pm.group(2).strip()
            verb = pm.group(1)
            if not _is_speech_verb(verb):
                continue  # 韩萧和冒号之间不是说话动词，跳过（可能是别人在说话）
            if any(s <= ps and pe <= e or ps <= s and e <= pe for ps, pe in used_spans):
                continue
            used_spans.append((s, e))
            out.append({
                "text": inner,
                "type": _type_of(verb),
                "verb": verb,
                "ctx_before": _ctx_before(line, pm.start()),
                "ctx_after": _ctx_after(line, pm.end()),
                "chapter": chapter,
            })

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="提取韩萧语料（高精度）")
    ap.add_argument("--txt", default=DEFAULT_TXT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    text = open(args.txt, encoding="gb18030", errors="replace").read()
    entries = extract(text)
    if args.limit:
        entries = entries[: args.limit]

    seen, uniq = set(), []
    for e in entries:
        k = (e["text"], e["type"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "hanxiao_lines.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for e in uniq:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    tc = Counter(e["type"] for e in uniq)
    print(f"提取 {len(entries)} 条，去重后 {len(uniq)} 条 → {out_path}")
    print(f"类型：{dict(tc)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
