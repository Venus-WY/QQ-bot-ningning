#!/usr/bin/env python3
"""
把原始对白切成「小互动场景单元」，作为人格蒸馏的基本单位。

与 build_context.py 的区别：
  - build_context.py 是「每条宁宁台词一个窗口」（单句，前后对称 4+4）
  - 本脚本是「每个小互动一个单元」：
        context（前文 6 句） + nene_response（宁宁回复，可能多句） + follow_up（后续 2 句）
    重点让模型看到「别人做了什么 → 宁宁怎么反应」。

处理要点：
  1. 连续出现的宁宁台词合并成一次「回复」（同一句话可能拆成多行）。
  2. 旁白作为独立说话人（"旁白"），保留在上下文里（旁白常点破情绪/动作）。
  3. 过滤纯语气词/拟声回复（"嗯…""哈啊……"），这些无语义、蒸馏无价值。
  4. 宁宁的别名（女生/绫地/宁宁＆柊史…）统一成「宁宁」。

输入 : adult.xp3 + scn.xp3 的解包产物（同 build_context.py）
输出 : corpus/scenes.jsonl
  每条形如：
    {
      "scene_id": "chapter11",
      "context": [{"speaker": "和奏", "text": "..."}, ...],
      "nene_response": "嗯？你们在叫我？",
      "follow_up": [{"speaker": "秀明", "text": "..."}, ...],
      "is_h": false
    }

用法 :
  python scripts/build_scenes.py [--ctx 6] [--follow 2] [--out <dir>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_context as bc               # noqa: E402  复用原始提取
from extract_nene import (               # noqa: E402
    DEFAULT_OUT_DIR,
    H_KEYWORDS,
    _load_psb_reader,
    is_h_scene,
    is_nene,
)

# 纯语气词/拟声/标点字符：去掉这些后若为空，判定为「无语义」直接跳过
_FILLER_CHARS = set(
    "嗯啊诶哈呼唔呜哦噢呃呀哎嗨嘿哟嘁啧哼嘛咯咧啾嘎啪啵咻嗖咚锵唧嘶嗬呐呸噢咿唔呣"
    "…～~。．、，！？!?·—－—（）()【】[]「」『』《》<>　\"'"
)


def _speaker_of(row: dict) -> str:
    """规范化说话人：宁宁→宁宁，旁白→旁白，其它用简体名。"""
    if is_nene(row):
        return "宁宁"
    return row["speaker_cn"] or "旁白"


def _is_trivial(text: str) -> bool:
    """无实际语义的纯语气词/拟声/标点回复。"""
    t = (text or "").strip()
    if len(t) <= 1:
        return True
    content = "".join(ch for ch in t if ch not in _FILLER_CHARS and not ch.isspace())
    return len(content) == 0


def build_scenes(rows_by_scene: dict, ctx_before: int, follow_up: int) -> list[dict]:
    """按场景切出小互动单元。"""
    out: list[dict] = []
    for (_, scene_label), rows in rows_by_scene.items():
        is_h = is_h_scene(scene_label)

        # 1) 切成 turn：同一说话人连续行合并（旁白独立成 turn）
        turns: list[tuple[str, list[str]]] = []
        for r in rows:
            spk = _speaker_of(r)
            if turns and turns[-1][0] == spk:
                turns[-1][1].append(r["text"])
            else:
                turns.append((spk, [r["text"]]))

        # 2) 展平回原始行序列，记录每个 turn 的行区间
        lines: list[tuple[str, str]] = []
        spans: list[tuple[str, int, int]] = []
        idx = 0
        for spk, texts in turns:
            for t in texts:
                lines.append((spk, t))
            spans.append((spk, idx, idx + len(texts)))
            idx += len(texts)

        # 3) 每个宁宁 turn 生成一个单元
        for spk, s, e in spans:
            if spk != "宁宁":
                continue
            resp = "\n".join(lines[i][1] for i in range(s, e))
            if _is_trivial(resp):
                continue

            ctx = [
                {"speaker": lines[i][0], "text": lines[i][1]}
                for i in range(max(0, s - ctx_before), s)
            ]
            fu = [
                {"speaker": lines[i][0], "text": lines[i][1]}
                for i in range(e, min(len(lines), e + follow_up))
            ]

            out.append(
                {
                    "scene_id": scene_label.lstrip("*"),
                    "context": ctx,
                    "nene_response": resp,
                    "follow_up": fu,
                    "is_h": is_h or any(k in resp for k in H_KEYWORDS),
                }
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="切分宁宁的小互动场景单元")
    ap.add_argument("--ctx", type=int, default=6, help="宁宁回复前的上下文行数")
    ap.add_argument("--follow", type=int, default=2, help="宁宁回复后的后续行数")
    ap.add_argument("--out", default=DEFAULT_OUT_DIR, help="输出目录")
    args = ap.parse_args()

    Reader = _load_psb_reader()
    rows_by_scene: dict = {}
    for aid, src_dir in enumerate(bc.CONTEXT_SOURCE_DIRS):
        for r in bc._raw_lines_per_archive(Reader, src_dir):
            rows_by_scene.setdefault((aid, r["scene"]), []).append(r)

    scenes = build_scenes(rows_by_scene, args.ctx, args.follow)
    clean = [s for s in scenes if not s["is_h"]]

    out_path = os.path.join(args.out, "scenes.jsonl")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for s in scenes:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"已切出 {len(scenes)} 个小互动单元 → {out_path}")
    print(f"其中正常剧情 {len(clean)} 个，H 场景 {len(scenes) - len(clean)} 个。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
