#!/usr/bin/env python3
"""
分模块人格蒸馏：从 scenes_tagged.jsonl 蒸馏绫地宁宁的人格规则。

四个模块，各自产出带「证据 ID」的规则（防脑补）：
  personality -> personality.yaml   核心人格
  speech      -> speech.yaml       语言辨识度（句长/语气词/否认/吐槽/犹豫）
  behavior    -> behavior.yaml     情境反应（被夸/被调侃/求助/吵架…）
  social      -> social.yaml       对陌生人/朋友/熟人/亲近对象的分层

关键机制：
  - 每个场景在加载时分配唯一 `_id`（形如 "0042:chapter48"），LLM 引用它作证据。
  - 落地前校验 evidence 里的 ID 真实存在，不存在的直接丢弃 —— 防止模型编造场景。
  - 采样分层（按关系档位/情绪/标签），保证覆盖面，而不是抓前 N 条。

运行时这些 YAML 是「只读人格层」，供 persona.py 拼进 system prompt，运行中不被修改。

用法 :
  python scripts/distill_persona.py --module personality          # 单个模块
  python scripts/distill_persona.py --module all                 # 全部四个
  python scripts/distill_persona.py --module speech --limit 200  # 用前 200 条验证
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

RNG = random.Random(20240907)  # 固定种子，可复现

# 关系档位（复用 classify_scenes 的词表）
STAGES = ["stranger", "acquaintance", "friend", "close_friend", "romantic", "family"]

# 情境 -> 标签映射：behavior 模块据此按标签取样本
SITUATIONS = {
    "被夸": ["compliment"],
    "被调侃": ["teasing"],
    "被戳破/害羞": ["embarrassed", "denial"],
    "生气/吵架": ["angry", "conflict"],
    "求助/帮忙": ["helping"],
    "安慰/对方低落": ["comfort", "sad"],
    "困惑/没听懂": ["confused"],
    "正经/严肃话题": ["serious"],
    "恋爱相关": ["romance_related"],
    "日常闲聊/开心": ["casual", "friendly", "happy", "playful", "curious"],
    "学校生活": ["school"],
    "陌生人搭话": ["stranger"],
}


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


def load_scenes(path: str) -> list[dict]:
    """读 scenes_tagged.jsonl，给每条分配唯一 _id。"""
    scenes = [json.loads(l) for l in open(path, encoding="utf-8")]
    for i, s in enumerate(scenes):
        s["_id"] = f"{i:04d}:{s.get('scene_id', '?')}"
    return scenes


def _clip(t: str, n: int = 40) -> str:
    t = (t or "").strip()
    return t if len(t) <= n else t[:n] + "…"


def render_scene(s: dict) -> str:
    """把场景压成紧凑文本喂给模型（前文只取最近 3 句）。"""
    ctx = " ".join(f"{c['speaker']}：{_clip(c['text'])}" for c in s["context"][-3:])
    fu = " ".join(f"{f['speaker']}：{_clip(f['text'])}" for f in s["follow_up"][:2])
    resp = _clip(s["nene_response"], 60).replace("\n", " ")
    parts = [f"【{s['_id']}】"]
    if ctx:
        parts.append(f"  前文：{ctx}")
    parts.append(f"  宁宁：{resp}")
    if fu:
        parts.append(f"  后续：{fu}")
    return "\n".join(parts)


def _ask_json(client: OpenAI, system: str, user: str, max_tokens: int) -> dict:
    """带重试的 JSON 问答（LLM 偶发残缺 JSON）。"""
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
        except (json.JSONDecodeError, Exception):
            time.sleep(1.0 * (attempt + 1))
    return last


def _valid_evidence(evidence, valid: set[str]) -> list[str]:
    """只保留真实存在的场景 ID，丢弃模型编造的。"""
    out = []
    for e in evidence or []:
        if isinstance(e, str) and e in valid:
            out.append(e)
    return out


def stratified_sample(scenes: list[dict], key: str, per: int, cap: int) -> list[dict]:
    """按 key 分层取样，每组最多 per 个，总数封顶 cap。"""
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for s in scenes:
        groups[s.get(key, "?")].append(s)
    picks: list[dict] = []
    for k, lst in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        picks.extend(RNG.sample(lst, min(per, len(lst))))
    if len(picks) > cap:
        picks = RNG.sample(picks, cap)
    return picks


def sample_by_tags(scenes: list[dict], tags: list[str], per: int) -> list[dict]:
    pool = [s for s in scenes if set(s["tags"]) & set(tags)]
    return RNG.sample(pool, min(per, len(pool))) if pool else []


# ---------------------------------------------------------------- personality

def distill_personality(client: OpenAI, scenes: list[dict], valid: set[str]) -> dict:
    sample = stratified_sample(scenes, "relationship_stage", per=8, cap=50)
    system = (
        "你是《魔女的夜宴》角色分析师。下面给你绫地宁宁的一批真实对话场景，每条带唯一 ID（形如 0042:chapter48）。\n"
        "请总结她的【核心人格】：她是一个什么样的人——性格底色、价值观、内心矛盾、处世方式。\n"
        "要求：提炼 6~10 条核心人格特质，每条包含：\n"
        "  - name: 简短命名（如「孤僻但渴望连接」）\n"
        "  - description: 一句话说明\n"
        "  - evidence: 1~3 个场景 ID（必须从下面给到的 ID 里选，不要自创）\n"
        "  - example: 一条她的原话作为例证（可从场景里摘，没有就留空字符串）\n"
        "只返回一个 JSON 对象，形如：\n"
        '{"traits": [{"name": "...", "description": "...", "evidence": ["0042:chapter48"], "example": "..."}]}'
    )
    user = "以下是宁宁的真实场景：\n\n" + "\n\n".join(render_scene(s) for s in sample)
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

def _speech_stats(scenes: list[dict]) -> dict:
    lens = [len(s["nene_response"]) for s in scenes]
    n = len(scenes)
    particles = "嗯啊诶呃唔呀哎嗨嘛呢吧啦哦噢"
    total_chars = sum(lens)
    total_particles = sum(
        1 for s in scenes for ch in s["nene_response"] if ch in particles
    )
    question = sum(
        1 for s in scenes
        if s["nene_response"].strip().endswith(("？", "?"))
        or any(k in s["nene_response"] for k in ("吗", "呢"))
    )
    exclam = sum(1 for s in scenes if "！" in s["nene_response"] or "!" in s["nene_response"])
    return {
        "count": n,
        "mean_chars": round(sum(lens) / n, 1) if n else 0,
        "median_chars": round(statistics.median(lens), 1) if n else 0,
        "particle_per_char": round(total_particles / total_chars, 4) if total_chars else 0,
        "question_rate": round(question / n, 3) if n else 0,
        "exclamation_rate": round(exclam / n, 3) if n else 0,
    }


def distill_speech(client: OpenAI, scenes: list[dict], valid: set[str]) -> dict:
    sample = stratified_sample(scenes, "emotion_state", per=5, cap=50)
    system = (
        "你是《魔女的夜宴》角色分析师。下面给你绫地宁宁的一批真实对白（每条带唯一 ID）。\n"
        "请总结她的【语言辨识度】：她说话有什么鲜明特点。分维度给出，维度可选（但不限于）：\n"
        "  句长、语气词/口头禅、被夸或被调侃时的否认、吐槽反击、犹豫时的表现、生气的表达、亲昵/感叹。\n"
        "每个维度下给 1~3 条 pattern，每条包含：\n"
        "  - category: 维度名\n"
        "  - pattern: 一条可复用的语言习惯描述\n"
        "  - example: 一条她的原话例证（从场景里摘）\n"
        "  - evidence: 1~2 个场景 ID（必须从下面给到的 ID 里选）\n"
        "只返回一个 JSON 对象，形如：\n"
        '{"patterns": [{"category": "否认", "pattern": "...", "example": "...", "evidence": ["0042:chapter48"]}]}'
    )
    user = "以下是宁宁的真实对白：\n\n" + "\n\n".join(render_scene(s) for s in sample)
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
    return {"module": "speech", "stats": _speech_stats(scenes), "patterns": patterns}


# ------------------------------------------------------------------- behavior

def distill_behavior(client: OpenAI, scenes: list[dict], valid: set[str]) -> dict:
    situations: dict[str, dict] = {}
    for sit, tags in SITUATIONS.items():
        sample = sample_by_tags(scenes, tags, per=6)
        if len(sample) < 2:
            continue  # 样本太少，跳过（如 stranger 标签只有 1 条）
        ids = [s["_id"] for s in sample]
        system = (
            "你是《魔女的夜宴》角色分析师。下面给你绫地宁宁在【" + sit + "】情境下的若干真实场景，"
            "每条带唯一 ID（形如 0042:chapter48）。\n"
            "总结她面对这种情境的典型反应模式。\n"
            "只返回一个 JSON 对象：\n"
            '{"reaction": "一句话描述她的典型反应", "evidence": ["从下面给到的 ID 里选 1~3 个"], "example": "一句原话"}\n'
            "evidence 必须从下面场景的 ID 里选，不要自创。"
        )
        user = "以下是宁宁在【" + sit + "】下的场景：\n\n" + "\n\n".join(render_scene(s) for s in sample)
        data = _ask_json(client, system, user, max_tokens=500)
        reaction = str(data.get("reaction", "")).strip()
        if not reaction:
            continue
        ev = _valid_evidence(data.get("evidence"), valid)
        if not ev:  # 模型没引证据 → 兜底用这批样本自身的 ID（它们本来就是证据）
            ev = ids
        situations[sit] = {
            "reaction": reaction,
            "example": str(data.get("example", "")).strip(),
            "evidence": ev,
        }
        time.sleep(0.3)
    return {"module": "behavior", "situations": situations}


# --------------------------------------------------------------------- social

def distill_social(client: OpenAI, scenes: list[dict], valid: set[str]) -> dict:
    sample = []
    stage_samples: dict[str, list[dict]] = {}
    for stage in STAGES:
        pool = [s for s in scenes if s["relationship_stage"] == stage]
        picks = RNG.sample(pool, min(4, len(pool))) if pool else []
        stage_samples[stage] = picks
        sample.extend(picks)
    system = (
        "你是《魔女的夜宴》角色分析师。下面给你绫地宁宁面对不同亲疏关系对象的场景"
        "（每条带唯一 ID，形如 0042:chapter48，已标注关系档位）。\n"
        "总结她在每个关系档位（stranger=陌生人, acquaintance=认识, friend=朋友, "
        "close_friend=亲近朋友, romantic=恋人, family=家人）下的说话语气与距离感。\n"
        "只返回一个 JSON 对象，键是档位英文名，值含 tone（语气描述）和 evidence（场景 ID 列表）：\n"
        '{"stranger": {"tone": "...", "evidence": ["从下面给到的 ID 里选 1~3 个"]}, ...}\n'
        "evidence 必须从下面场景的 ID 里选，不要自创。"
    )
    user = "以下是宁宁在不同关系下的场景：\n\n" + "\n\n".join(render_scene(s) for s in sample)
    data = _ask_json(client, system, user, max_tokens=2500)

    stages = {}
    for stage in STAGES:
        st = data.get(stage) or {}
        tone = str(st.get("tone", "")).strip()
        ev = _valid_evidence(st.get("evidence"), valid)
        if not ev:  # 兜底：用该档位样本自身的 ID
            ev = [s["_id"] for s in stage_samples.get(stage, [])]
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
    import yaml  # noqa: E402  (config.py 已依赖，venv 里有)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{data['module']}.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return path


def _summary(data: dict) -> str:
    m = data["module"]
    if m == "personality":
        return f"{len(data['traits'])} 条特质：" + "、".join(t["name"] for t in data["traits"])
    if m == "speech":
        cats = collections.Counter(p["category"] for p in data["patterns"])
        return f"{len(data['patterns'])} 条语言规则（" + "、".join(f"{k}×{v}" for k, v in cats.items()) + "）"
    if m == "behavior":
        return f"{len(data['situations'])} 个情境：" + "、".join(data["situations"].keys())
    if m == "social":
        return f"{len(data['stages'])} 个关系档位：" + "、".join(data["stages"].keys())
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="分模块蒸馏绫地宁宁人格")
    ap.add_argument("--module", default="all", help="personality/speech/behavior/social/all")
    ap.add_argument("--limit", type=int, default=0, help="只用前 N 条验证（0=全量）")
    ap.add_argument("--in", dest="in_path", default=os.path.join(CORPUS, "scenes_tagged.jsonl"))
    args = ap.parse_args()

    scenes = load_scenes(args.in_path)
    if args.limit:
        scenes = scenes[: args.limit]
    valid = {s["_id"] for s in scenes}
    print(f"语料 {len(scenes)} 条场景，准备蒸馏。")

    names = list(MODULES) if args.module == "all" else [args.module]
    client = _client()
    for name in names:
        fn = MODULES[name]
        print(f"\n=== 蒸馏 {name} ===")
        try:
            data = fn(client, scenes, valid)
        except Exception as exc:
            print(f"  [失败] {name}：{exc}")
            continue
        path = write_yaml(data)
        print(f"  → {path}")
        print(f"  → {_summary(data)}")

    print("\n完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
