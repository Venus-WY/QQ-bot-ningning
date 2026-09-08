#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
韩萧人格蒸馏 —— 从 hanxiao_lines.jsonl 蒸馏《超神机械师》韩萧的 AI 群友人格。

输出（覆盖 corpus/persona/ 下原宁宁产物）：
  personality.yaml  核心人格（traits，带证据）
  speech.yaml       语言习惯（本地统计 + LLM 提炼 patterns）
  behavior.yaml     情境反应（situations）
  social.yaml       关系档位语气（stages）
  以及 corpus/fewshot.jsonl

用法 :
  python scripts/distill_hanxiao.py --module personality [--limit 200]
  python scripts/distill_hanxiao.py --module speech
  python scripts/distill_hanxiao.py --module all
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
QQ_BOT = os.path.join(ROOT, "qq-bot")
CORPUS = os.path.join(ROOT, "corpus")
OUT_DIR = os.path.join(CORPUS, "persona")

sys.path.insert(0, os.path.join(QQ_BOT, ".venv", "Lib", "site-packages"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(QQ_BOT, ".env"))

from openai import OpenAI  # noqa: E402

RNG = random.Random(20240907)

# 韩萧情境标签（用于 behavior 模块按标签采样 + fewshot 的 tag 词表）
SITUATIONS = {
    "被质疑/被挑衅": ["质疑", "挑衅", "威胁", "敌对", "战斗"],
    "谈判/交易": ["谈判", "交易", "合作", "条件"],
    "被求助/委托": ["求助", "委托", "请求", "任务"],
    "危机/遇险": ["危机", "危险", "战斗", "逃"],
    "日常吐槽/毒舌": ["吐槽", "调侃", "毒舌", "玩笑"],
    "冷静分析/布局": ["分析", "计划", "算计", "推理"],
    "装逼/打脸": ["装逼", "打脸", "震慑", "示威"],
    "制造/机械": ["机械", "制造", "装备", "技术"],
    "队友/同伴互动": ["同伴", "队友", "朋友", "熟人"],
    "陌生人/敌对势力": ["陌生人", "敌人", "势力"],
}


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


def load_lines(path: str) -> list[dict]:
    lines = [json.loads(l) for l in open(path, encoding="utf-8")]
    for i, s in enumerate(lines):
        s["_id"] = f"{i:04d}:{s.get('chapter', '?')[:12]}"
    return lines


def _clip(t: str, n: int = 50) -> str:
    t = (t or "").strip()
    return t if len(t) <= n else t[:n] + "…"


def render_line(s: dict) -> str:
    """把一条韩萧语料压成紧凑文本。"""
    parts = [f"【{s['_id']}】"]
    if s.get("ctx_before"):
        parts.append(f"  前文：{_clip(s['ctx_before'], 60)}")
    tag = "独白" if s["type"] == "inner" else "对白"
    parts.append(f"  韩萧{tag}：{_clip(s['text'], 80)}")
    if s.get("ctx_after"):
        parts.append(f"  后续：{_clip(s['ctx_after'], 60)}")
    return "\n".join(parts)


def _ask_json(client: OpenAI, system: str, user: str, max_tokens: int) -> dict:
    last = {}
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
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


def _valid_evidence(evidence, valid: set[str]) -> list[str]:
    out = []
    for e in evidence or []:
        if isinstance(e, str) and e in valid:
            out.append(e)
    return out


def stratified_sample(lines: list[dict], key: str, per: int, cap: int) -> list[dict]:
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for s in lines:
        groups[s.get(key, "?")].append(s)
    picks: list[dict] = []
    for k, lst in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        picks.extend(RNG.sample(lst, min(per, len(lst))))
    if len(picks) > cap:
        picks = RNG.sample(picks, cap)
    return picks


# ---------------------------------------------------------------- personality

def distill_personality(client: OpenAI, lines: list[dict], valid: set[str]) -> dict:
    # 内心独白最能体现真实性格，对白体现社交表现；两者都采样
    inner = [s for s in lines if s["type"] == "inner"]
    spoken = [s for s in lines if s["type"] == "spoken"]
    sample = (RNG.sample(inner, min(40, len(inner))) +
              RNG.sample(spoken, min(60, len(spoken))))
    system = (
        "你是小说《超神机械师》的角色分析师。下面给你主角韩萧的一批真实对白与内心独白，"
        "每条带唯一 ID（形如 0042:chapter01）。\n"
        "请总结韩萧的【核心人格】：他是什么样的人——性格底色、价值观、处世方式、说话风格。\n"
        "要求：提炼 6~10 条核心人格特质，每条包含：\n"
        "  - name: 简短命名（如「冷静理性的实用主义者」）\n"
        "  - description: 一句话说明\n"
        "  - evidence: 1~3 个场景 ID（必须从下面给到的 ID 里选，不要自创）\n"
        "  - example: 一条他的原话作为例证（可从场景里摘，没有就留空字符串）\n"
        "只返回一个 JSON 对象，形如：\n"
        '{"traits": [{"name": "...", "description": "...", "evidence": ["0042:chapter01"], "example": "..."}]}'
    )
    user = "以下是韩萧的真实语料：\n\n" + "\n\n".join(render_line(s) for s in sample)
    data = _ask_json(client, system, user, max_tokens=3000)

    traits = []
    for t in data.get("traits", []):
        name = str(t.get("name", "")).strip()
        desc = str(t.get("description", "")).strip()
        if not name or not desc:
            continue
        traits.append({
            "name": name,
            "description": desc,
            "evidence": _valid_evidence(t.get("evidence"), valid),
            "example": str(t.get("example", "")).strip(),
        })
    return {"module": "personality", "traits": traits}


# --------------------------------------------------------------------- speech

def _speech_stats(lines: list[dict]) -> dict:
    texts = [s["text"] for s in lines if s["type"] == "spoken"]
    n = len(texts)
    lens = [len(t) for t in texts]
    particles = "嗯啊诶呃唔呀哎嗨嘛呢吧啦哦噢啧哼呵"
    total_chars = sum(lens)
    total_particles = sum(1 for t in texts for ch in t if ch in particles)
    question = sum(1 for t in texts if t.strip().endswith(("？", "?")) or any(k in t for k in ("吗", "呢")))
    exclam = sum(1 for t in texts if "！" in t or "!" in t)
    return {
        "count": n,
        "mean_chars": round(sum(lens) / n, 1) if n else 0,
        "median_chars": round(statistics.median(lens), 1) if n else 0,
        "particle_per_char": round(total_particles / total_chars, 4) if total_chars else 0,
        "question_rate": round(question / n, 3) if n else 0,
        "exclamation_rate": round(exclam / n, 3) if n else 0,
    }


def distill_speech(client: OpenAI, lines: list[dict], valid: set[str]) -> dict:
    spoken = [s for s in lines if s["type"] == "spoken"]
    sample = RNG.sample(spoken, min(60, len(spoken)))
    system = (
        "你是小说《超神机械师》的角色分析师。下面给你主角韩萧的一批真实对白（每条带唯一 ID）。\n"
        "请总结韩萧的【语言辨识度】：他说话有什么鲜明特点。分维度给出，维度可选（但不限于）：\n"
        "  句长、语气词/口头禅、毒舌吐槽、理性分析口吻、被质疑时的回击、谈判/装逼、冷幽默、敷衍/漫不经心。\n"
        "每个维度下给 1~3 条 pattern，每条包含：\n"
        "  - category: 维度名\n"
        "  - pattern: 一条可复用的语言习惯描述\n"
        "  - example: 一条他的原话例证（从场景里摘）\n"
        "  - evidence: 1~2 个场景 ID（必须从下面给到的 ID 里选）\n"
        "只返回一个 JSON 对象，形如：\n"
        '{"patterns": [{"category": "毒舌吐槽", "pattern": "...", "example": "...", "evidence": ["0042:chapter01"]}]}'
    )
    user = "以下是韩萧的真实对白：\n\n" + "\n\n".join(render_line(s) for s in sample)
    data = _ask_json(client, system, user, max_tokens=3000)

    patterns = []
    for p in data.get("patterns", []):
        cat = str(p.get("category", "")).strip()
        pat = str(p.get("pattern", "")).strip()
        if not cat or not pat:
            continue
        patterns.append({
            "category": cat,
            "pattern": pat,
            "example": str(p.get("example", "")).strip(),
            "evidence": _valid_evidence(p.get("evidence"), valid),
        })
    return {"module": "speech", "stats": _speech_stats(lines), "patterns": patterns}


# ------------------------------------------------------------------- behavior

def distill_behavior(client: OpenAI, lines: list[dict], valid: set[str]) -> dict:
    situations: dict[str, dict] = {}
    spoken = [s for s in lines if s["type"] == "spoken"]
    # 韩萧的情境多样，直接按大类让 LLM 总结；这里分 3 批喂，让 LLM 按情境分类总结
    batches = [spoken[i:i + 50] for i in range(0, min(len(spoken), 150), 50)]
    all_raw = {}
    for bi, batch in enumerate(batches):
        system = (
            "你是小说《超神机械师》的角色分析师。下面给你主角韩萧的一批真实对白（每条带唯一 ID）。\n"
            "请总结韩萧面对不同情境的典型反应模式。情境可选：被质疑/挑衅、谈判交易、被求助、危机、"
            "日常毒舌吐槽、冷静分析布局、装逼打脸、制造机械、队友互动、对陌生人/敌人。\n"
            "只返回一个 JSON 对象，键是情境名，值含 reaction（一句话典型反应）和 evidence（场景 ID 列表）：\n"
            '{"被质疑/挑衅": {"reaction": "...", "evidence": ["0042:chapter01"]}, ...}\n'
            "evidence 必须从下面场景的 ID 里选，不要自创。"
        )
        user = "以下是韩萧的对白：\n\n" + "\n\n".join(render_line(s) for s in batch)
        data = _ask_json(client, system, user, max_tokens=2500)
        for sit, v in (data.items() if isinstance(data, dict) else []):
            if not isinstance(v, dict):
                continue
            reaction = str(v.get("reaction", "")).strip()
            if not reaction:
                continue
            all_raw.setdefault(sit, {"reaction": reaction, "evidence": [], "example": ""})
            all_raw[sit]["evidence"] += _valid_evidence(v.get("evidence"), valid)
        time.sleep(0.3)

    for sit, v in all_raw.items():
        v["evidence"] = list(dict.fromkeys(v["evidence"]))[:3]
        situations[sit] = {"reaction": v["reaction"], "evidence": v["evidence"], "example": ""}
    return {"module": "behavior", "situations": situations}


# --------------------------------------------------------------------- social

def distill_social(client: OpenAI, lines: list[dict], valid: set[str]) -> dict:
    spoken = [s for s in lines if s["type"] == "spoken"]
    sample = RNG.sample(spoken, min(60, len(spoken)))
    system = (
        "你是小说《超神机械师》的角色分析师。下面给你主角韩萧面对不同对象的对白（每条带唯一 ID）。\n"
        "总结他面对陌生人/敌人、普通熟人、朋友队友、亲近之人时的说话语气与距离感。\n"
        "只返回一个 JSON 对象，键为：stranger（陌生人/敌人）、acquaintance（普通熟人）、"
        "friend（朋友队友）、close_friend（亲近之人）。每项含 tone（语气描述）和 evidence（场景 ID 列表）：\n"
        '{"stranger": {"tone": "...", "evidence": ["0042:chapter01"]}, ...}\n'
        "evidence 必须从下面场景的 ID 里选，不要自创。"
    )
    user = "以下是韩萧的对白：\n\n" + "\n\n".join(render_line(s) for s in sample)
    data = _ask_json(client, system, user, max_tokens=2500)

    stages = {}
    for stage in ["stranger", "acquaintance", "friend", "close_friend"]:
        st = data.get(stage) or {}
        tone = str(st.get("tone", "")).strip()
        ev = _valid_evidence(st.get("evidence"), valid)
        if tone or ev:
            stages[stage] = {"tone": tone, "evidence": ev}
    return {"module": "social", "stages": stages}


# --------------------------------------------------------------------- driver

MODULES = {
    "personality": distill_personality,
    "speech": distill_speech,
    "behavior": distill_behavior,
    "social": distill_social,
}


def write_yaml(data: dict) -> str:
    import yaml  # noqa: E402
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{data['module']}.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="蒸馏韩萧人格")
    ap.add_argument("--module", default="all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--in", dest="in_path", default=os.path.join(CORPUS, "hanxiao_lines.jsonl"))
    args = ap.parse_args()

    lines = load_lines(args.in_path)
    if args.limit:
        lines = lines[: args.limit]
    valid = {s["_id"] for s in lines}
    print(f"语料 {len(lines)} 条，准备蒸馏韩萧人格。")

    names = list(MODULES) if args.module == "all" else [args.module]
    client = _client()
    for name in names:
        fn = MODULES[name]
        print(f"\n=== 蒸馏 {name} ===")
        try:
            data = fn(client, lines, valid)
        except Exception as exc:
            print(f"  [失败] {name}：{exc}")
            continue
        path = write_yaml(data)
        print(f"  → {path}")
        m = data["module"]
        if m == "personality":
            print(f"  → {len(data['traits'])} 条特质")
        elif m == "speech":
            print(f"  → {len(data['patterns'])} 条语言规则，stats={data['stats']}")
        elif m == "behavior":
            print(f"  → {len(data['situations'])} 个情境")
        elif m == "social":
            print(f"  → {len(data['stages'])} 个关系档位")

    print("\n完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
