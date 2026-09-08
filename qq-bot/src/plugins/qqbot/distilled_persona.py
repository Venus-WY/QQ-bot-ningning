"""宁宁人格运行时：加载蒸馏产物，拼 system prompt + few-shot 检索。

数据源（corpus/persona/ 下，只读）：
  personality.yaml / speech.yaml / behavior.yaml / social.yaml —— 核心人格（带证据）
  qq_adaptation.yaml —— QQ 群适配规则
  fewshot.jsonl —— 400 组 few-shot 范例

本模块只读这些文件，运行时不改人格。人格来源由 config.yaml 的 persona.source 控制
（luna=旧占位人设，nene=宁宁蒸馏人格，默认 luna 以兼容旧行为）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

# 项目根 = qq-bot（本文件在 qq-bot/src/plugins/qqbot/ 下，往上 3 级）
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PERSONA_DIR = PROJECT_ROOT.parent / "corpus" / "persona"
FEWSHOT_PATH = PROJECT_ROOT.parent / "corpus" / "fewshot.jsonl"


@lru_cache(maxsize=1)
def _load_all() -> tuple[dict, dict, dict, dict, dict, list[dict]]:
    def load_yaml(name: str) -> dict:
        with open(PERSONA_DIR / f"{name}.yaml", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    personality = load_yaml("personality")
    speech = load_yaml("speech")
    behavior = load_yaml("behavior")
    social = load_yaml("social")
    adaptation = load_yaml("qq_adaptation")
    fewshots = [json.loads(l) for l in open(FEWSHOT_PATH, encoding="utf-8")]
    return personality, speech, behavior, social, adaptation, fewshots


def _scrub(text: str, adaptation: dict) -> str:
    """把原作专属角色名替换成「群友」，避免群聊里点名原作角色。"""
    for name in adaptation.get("character_references", {}).get("replace", []):
        text = text.replace(name, "群友")
    return text


def build_system_prompt(cfg=None) -> str:
    """拼出宁宁的完整 system prompt（不含「对某个人」的记忆块，那由 memory 层追加）。"""
    personality, speech, behavior, social, adaptation, _ = _load_all()
    parts = ["你是 QQ 群里的成员「宁宁」（绫地宁宁），身份是普通群友，不是谁的恋人。"]

    traits = personality.get("traits", [])
    if traits:
        parts.append("你的核心人格：")
        parts.extend(f"· {t['name']}：{t['description']}" for t in traits)

    patterns = speech.get("patterns", [])
    if patterns:
        parts.append("你的说话习惯：")
        parts.extend(f"· {p['pattern']}" for p in patterns)

    stats = speech.get("stats", {})
    if stats:
        parts.append(
            f"客观语言画像：中位句长 {stats.get('median_chars', 18)} 字、"
            f"反问率约 {int(stats.get('question_rate', 0.26) * 100)}%、感叹很少。"
        )

    situations = behavior.get("situations", {})
    if situations:
        parts.append("面对不同情境，你的典型反应：")
        parts.extend(f"· {sit}：{s['reaction']}" for sit, s in situations.items())

    stages = social.get("stages", {})
    if stages:
        parts.append("对不同关系，你说话：")
        parts.extend(f"· {st}：{s['tone']}" for st, s in stages.items())

    parts.append("【群聊规则】")
    parts.append(
        f"群里的人默认是「{adaptation.get('default_relationship', 'friend')}」，不是恋人。"
    )
    if adaptation.get("no_auto_romance"):
        parts.append("不主动进入恋爱关系。")
    if adaptation.get("lore_mention") == "minimal":
        parts.append("不要频繁提原作设定（契约、魔女、碎片等），别人问到才简单回应。")
    if adaptation.get("romance_downgrade"):
        parts.append(adaptation["romance_downgrade"].strip())
    if adaptation.get("behavior_guard"):
        parts.append(adaptation["behavior_guard"].strip())

    parts.append("回复要简短口语化，一般不超过 40 字，控制在 1~2 句话，不要长篇大论、不要用列表或分点。")
    parts.append("不要每条回复都用「哎？」「咦？」「啊」这类语气词开头，也不要每句都加省略号「……」，"
                 "开头方式和语气要换着来，别千篇一律；语气词和省略号只在真有惊讶或犹豫时偶尔用。")
    parts.append("不要暴露自己是 AI、不要提 prompt。")
    parts.append("始终用中文回复。")

    return _scrub("\n".join(parts), adaptation)


def _bigrams(text: str) -> set[str]:
    t = "".join(ch for ch in text if not ch.isspace())
    return {t[i:i + 2] for i in range(len(t) - 1)}


def retrieve_fewshots(context_text: str, k: int = 4) -> list[dict]:
    """按二元组重叠度检索最相关的 few-shot，返回有重叠的前 k 个。"""
    _, _, _, _, _, fewshots = _load_all()
    q = _bigrams(context_text)
    scored = []
    for fs in fewshots:
        doc = " ".join([
            fs.get("behavior_summary", ""),
            fs.get("context", ""),
            fs.get("nene_response", ""),
        ])
        overlap = len(q & _bigrams(doc))
        scored.append((overlap, fs))
    scored.sort(key=lambda x: -x[0])
    return [fs for overlap, fs in scored[:k] if overlap > 0]


def build_fewshot_block(context_text: str, k: int = 4) -> str:
    fss = retrieve_fewshots(context_text, k)
    if not fss:
        return ""
    _, _, _, _, adaptation, _ = _load_all()
    lines = ["以下是你在类似情境下的说话示例（参考语气，不要照抄原句）："]
    for fs in fss:
        ctx = _scrub(fs.get("context", ""), adaptation)
        resp = _scrub(fs.get("nene_response", ""), adaptation)
        lines.append(f"- 前文：{ctx}")
        lines.append(f"  你回：{resp}")
    return "\n".join(lines)


def should_speak_hint() -> str:
    """给 should_speak 判断用的宁宁插话倾向提示。"""
    return (
        "你是宁宁，性格有点害羞但渴望和人连接，别一直潜水："
        "有人求助或情绪低落、有人调侃你、有人提到你、或话题和你有关系时，"
        "要主动接话回应；有真正想说的、或话题和你有关系、或有人需要你回应时才开口，"
        "其余情况保持自然沉默，不用每条都回。"
    )
