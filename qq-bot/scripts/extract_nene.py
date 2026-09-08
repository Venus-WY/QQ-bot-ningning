#!/usr/bin/env python3
"""
《魔女的夜宴》剧本台词提取 —— 从三个 XP3 剧本包解出「说话人 + 中文台词」，
合并去重，筛出绫地宁宁（宁宁）的台词，并区分「正常剧情 / H 场景」。

剧本分布在三个包（都是 PSB 剧本，只是存放位置不同）：
  - corpus/extracted/psb/*.psb           ← scn.xp3（角色路线 + H 场景，26 个）
  - corpus/extracted_allage/allage/*.bin  ← allage.xp3（全年龄主体，80 个，被 adult 包含）
  - corpus/extracted_adult/adult/*.bin    ← adult.xp3（成人版主体，77 个，最全）

输出 :
  corpus/dialogue_all.jsonl    全量台词（去重，含说话人 + 中/日文）
  corpus/nene_lines.jsonl      宁宁全部台词（去重，含 is_h 标记）
  corpus/nene_lines_clean.jsonl 宁宁正常剧情台词（剔除 H 场景，用于人设蒸馏）

依赖 : 复用 hktkqj/cxdec-hxv4-static-analysis 的 psb_parser.PSBReader（仅修正字符串为 UTF-8 解码）。

用法 :
  python scripts/extract_nene.py
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import zlib
from collections import Counter

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # 创发面试/
TOOLS_REPO = os.path.join(
    ROOT, "corpus", "tools", "cxdec-hxv4-static-analysis-main"
)
# 三个剧本包的解包产物目录
SOURCE_DIRS = [
    os.path.join(ROOT, "corpus", "extracted", "psb"),        # scn.xp3（.psb）
    os.path.join(ROOT, "corpus", "extracted_allage", "allage"),  # allage.xp3（.bin）
    os.path.join(ROOT, "corpus", "extracted_adult", "adult"),    # adult.xp3（.bin）
]
DEFAULT_OUT_DIR = os.path.join(ROOT, "corpus")

# 宁宁在脚本里的称呼（日文 + 简体中文）
NENE_JP_NAMES = {"寧々", "子供寧々"}
NENE_CN_NAME = "宁宁"

# H 场景判定：编号区段（成人补丁新增的 H 章节） + 章节名
H_SECTION_NUMBERS = {"112", "115", "117", "214", "216", "217", "219",
                     "321", "412", "508"}
H_CHAPTERS = {"chapter23", "chapter24"}

# 成人内容关键词（用于行级兜底，剔除混合章节里漏网的 H 台词）
H_KEYWORDS = (
    "射精", "阴蒂", "龟头", "肉棒", "阴唇", "乳头", "乳首", "阴道", "小穴",
    "内射", "发情", "勃起", "自慰", "口交", "交合", "抽插", "淫乱", "淫荡",
    "精液", "阴茎", "阴囊", "爱液", "性器", "直插", "小鸡鸡", "淫水", "揉胸",
)


# ---------------------------------------------------------------------------
# PSBReader（UTF-8 字符串）
# ---------------------------------------------------------------------------
def _load_psb_reader():
    tools_dir = os.path.join(TOOLS_REPO, "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from psb_parser import PSBReader  # noqa: F401

    class Utf8PSBReader(PSBReader):
        """PSBReader，但字符串池按 UTF-8 解码（原实现按 ASCII，会抹掉中文）。"""

        def get_string(self, index: int) -> str:
            arr = self.read_string_offsets()
            start = self.header.offset_strings_data + arr.values[index]
            end = self._data.index(0, start)
            return self._data[start:end].decode("utf-8", errors="replace")

    return Utf8PSBReader


def _strip_quotes(text: str) -> str:
    """去掉台词首尾的日文引号「」与空白，得到更干净的台词文本。"""
    text = (text or "").strip()
    while text.startswith("「") and text.endswith("」") and len(text) >= 2:
        text = text[1:-1].strip()
    return text


def is_h_scene(label: str) -> bool:
    """按场景标签判断是否为 H 场景。"""
    if "_H_" in label:
        return True
    m = re.match(r"\*(\d+)", label)
    if m and m.group(1) in H_SECTION_NUMBERS:
        return True
    return label in H_CHAPTERS


# ---------------------------------------------------------------------------
# 提取逻辑
# ---------------------------------------------------------------------------
def extract_dialogue(source_dirs: list[str], Reader) -> list[dict]:
    """遍历所有剧本包，提取全部台词条目（每条含场景标签 + 说话人 + 中/日文）。"""
    entries: list[dict] = []
    tmp_psb = os.path.join(os.path.dirname(source_dirs[0]), "_tmp.psb")

    for src_dir in source_dirs:
        pattern = "*.psb" if src_dir.endswith("psb") else "*.bin"
        files = sorted(glob.glob(os.path.join(src_dir, pattern)))
        for fp in files:
            data = open(fp, "rb").read()
            # .bin 文件可能带 mdf 压缩头（magic b"mdf\x00" + u32 解压后长度 + zlib）
            if data[:4] == b"mdf\x00":
                data = zlib.decompress(data[8:])
            if data[:4] != b"PSB\x00":
                continue  # 非剧本（图片/语音等）

            with open(tmp_psb, "wb") as f:
                f.write(data)
            tree = Reader(tmp_psb).read_object_tree()

            for scene in tree.get("scenes", []):
                label = scene.get("label", "")
                for t in scene.get("texts", []):
                    # 结构：[说话人, [日文, cn, tw, ...], 语音, 时长, 附加]
                    speaker_jp = t[0]
                    lang_arr = t[1] if len(t) > 1 else []
                    jp = lang_arr[0] if len(lang_arr) > 0 else None
                    cn = lang_arr[1] if len(lang_arr) > 1 else None

                    text_jp = jp[1] if jp and len(jp) > 1 else ""
                    text_cn = cn[1] if cn and len(cn) > 1 else ""
                    speaker_cn = cn[0] if cn and len(cn) > 0 else None

                    if not text_cn:
                        continue  # 无中文字幕的条目跳过

                    entries.append(
                        {
                            "scene": label,
                            "speaker_jp": speaker_jp,
                            "speaker_cn": speaker_cn,
                            "text": _strip_quotes(text_cn),
                            "text_jp": _strip_quotes(text_jp),
                        }
                    )
    return entries


def dedup(entries: list[dict]) -> list[dict]:
    """按 (场景, 说话人, 中文台词) 去重，保持首次出现顺序。"""
    seen: set[tuple] = set()
    out: list[dict] = []
    for e in entries:
        key = (e["scene"], e["speaker_cn"], e["text"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def is_nene(entry: dict) -> bool:
    """判断该条台词是否属于宁宁（精确匹配，排除「宁宁的父亲」「宁宁＆䌷」等）。"""
    return (
        entry["speaker_cn"] == NENE_CN_NAME
        or entry["speaker_jp"] in NENE_JP_NAMES
    )


def write_jsonl(entries: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"已写出 {len(entries)} 条 → {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="提取魔女的夜宴台词并筛出宁宁")
    ap.add_argument("--out", default=DEFAULT_OUT_DIR, help="输出目录")
    args = ap.parse_args()

    Reader = _load_psb_reader()
    all_entries = extract_dialogue(SOURCE_DIRS, Reader)
    all_entries = dedup(all_entries)

    nene_entries = [e for e in all_entries if is_nene(e)]
    for e in nene_entries:
        # 场景标签判定 + 内容关键词兜底（混合章节里的 H 台词也要剔除）
        e["is_h"] = is_h_scene(e["scene"]) or any(
            k in e["text"] for k in H_KEYWORDS
        )
    nene_clean = [e for e in nene_entries if not e["is_h"]]

    # 说话人统计（验证用）
    cn_counter: Counter = Counter(e["speaker_cn"] for e in all_entries)
    print("说话人（简体）分布 Top 10：")
    for name, n in cn_counter.most_common(10):
        print(f"  {n:6d}  {name!r}")

    write_jsonl(all_entries, os.path.join(args.out, "dialogue_all.jsonl"))
    write_jsonl(nene_entries, os.path.join(args.out, "nene_lines.jsonl"))
    write_jsonl(nene_clean, os.path.join(args.out, "nene_lines_clean.jsonl"))

    n_h = len(nene_entries) - len(nene_clean)
    print(f"\n总台词 {len(all_entries)} 句；宁宁 {len(nene_entries)} 句"
          f"（正常 {len(nene_clean)} + H 场景 {n_h}）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
