#!/usr/bin/env python3
"""
把宁宁的台词重组成「上下文窗口」格式，供人格行为蒸馏使用。

动机：同一句「你笨蛋！」脱离上下文无法判断是
  真生气 / 被调侃后的羞恼 / 朋友间玩笑 —— 这正是 Persona 最需要的信息。
所以给每条宁宁台词附上它前后几行的说话人与台词。

输入 : adult.xp3 + scn.xp3 的解包产物（跳过 allage.xp3，它是 adult 的全年龄子集，冗余）
输出 : corpus/nene_context.jsonl
  每条形如：
    {
      "scene": "chapter16",
      "context_before": [{"speaker": "柊史", "text": "..."}, ...],
      "target": {"speaker": "宁宁", "text": "啊，保科？今天有什么事吗？"},
      "context_after":  [{"speaker": "旁白", "text": "..."}, ...],
      "is_h": false
    }

用法 :
  python scripts/build_context.py [--window N]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # 复用 extract_nene 里的 Reader / 判定
import extract_nene as ex  # noqa: E402

# 上下文来源：adult（主体）+ scn（路线/H），不要 allage（冗余子集）
CONTEXT_SOURCE_DIRS = [
    ex.SOURCE_DIRS[2],  # adult.xp3
    ex.SOURCE_DIRS[0],  # scn.xp3
]


def _raw_lines_per_archive(Reader, src_dir: str) -> list[dict]:
    """提取单个包的全部台词，保留原始顺序（不去重），并带 archive 标记。"""
    rows: list[dict] = []
    tmp = os.path.join(os.path.dirname(src_dir), "_tmp.psb")
    pattern = "*.psb" if src_dir.endswith("psb") else "*.bin"
    for fp in sorted(glob.glob(os.path.join(src_dir, pattern))):
        data = open(fp, "rb").read()
        if data[:4] == b"mdf\x00":
            data = zlib.decompress(data[8:])
        if data[:4] != b"PSB\x00":
            continue
        with open(tmp, "wb") as f:
            f.write(data)
        tree = Reader(tmp).read_object_tree()
        for scene in tree.get("scenes", []):
            label = scene.get("label", "")
            for t in scene.get("texts", []):
                speaker_jp = t[0]
                lang_arr = t[1] if len(t) > 1 else []
                cn = lang_arr[1] if len(lang_arr) > 1 else None
                text_cn = cn[1] if cn and len(cn) > 1 else ""
                if not text_cn:
                    continue
                rows.append(
                    {
                        "scene": label,
                        "speaker_jp": speaker_jp,
                        "speaker_cn": cn[0] if cn else None,  # None = 旁白
                        "text": ex._strip_quotes(text_cn),
                    }
                )
    return rows


def build(rows_by_scene: dict, window: int) -> list[dict]:
    """对每个场景的台词序列，为每条宁宁台词生成上下文窗口。"""
    out: list[dict] = []
    for key, rows in rows_by_scene.items():
        scene_label = key[1]
        is_h = ex.is_h_scene(scene_label)
        n = len(rows)
        for i, r in enumerate(rows):
            if not ex.is_nene(r):
                continue
            before = rows[max(0, i - window):i]
            after = rows[i + 1:i + 1 + window]

            def fmt(rr):
                # 宁宁在不同阶段被标成「女生/绫地/宁宁＆柊史」等，统一成「宁宁」
                name = "宁宁" if ex.is_nene(rr) else (rr["speaker_cn"] or "旁白")
                return {
                    "speaker": name,
                    "text": rr["text"],
                }

            out.append(
                {
                    "scene": scene_label.lstrip("*"),
                    "context_before": [fmt(rr) for rr in before],
                    "target": fmt(r),
                    "context_after": [fmt(rr) for rr in after],
                    "is_h": is_h or any(
                        k in r["text"] for k in ex.H_KEYWORDS
                    ),
                }
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=4,
                    help="每条台词前后各取多少行作上下文")
    ap.add_argument("--out", default=ex.DEFAULT_OUT_DIR, help="输出目录")
    args = ap.parse_args()

    Reader = ex._load_psb_reader()

    # 按 (archive_id, scene) 分组，保证不同包里同名场景不串线
    rows_by_scene: dict = {}
    for aid, src_dir in enumerate(CONTEXT_SOURCE_DIRS):
        for r in _raw_lines_per_archive(Reader, src_dir):
            rows_by_scene.setdefault((aid, r["scene"]), []).append(r)

    results = build(rows_by_scene, args.window)
    nene_clean = [r for r in results if not r["is_h"]]

    out_path = os.path.join(args.out, "nene_context.jsonl")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"已写出 {len(results)} 条上下文 → {out_path}")
    print(f"其中正常剧情 {len(nene_clean)} 条，H 场景 "
          f"{len(results) - len(nene_clean)} 条。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
