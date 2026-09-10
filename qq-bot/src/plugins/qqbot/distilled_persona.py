"""蒸馏人格运行时：加载 corpus/persona 下的蒸馏产物，拼 system prompt + few-shot 检索。

数据源（corpus/persona/ 下，只读）：
  personality.yaml / speech.yaml / behavior.yaml / social.yaml —— 核心人格（带证据）
  qq_adaptation.yaml —— QQ 群适配规则（含角色背景记忆、恋爱降格、安全护栏、插话倾向）
  fewshot.jsonl —— few-shot 范例

本模块只读这些文件，运行时不改人格。角色名/身份等由 config.yaml 的 persona 配置提供，
人格来源由 config.yaml 的 persona.source 控制（蒸馏人格 vs 旧占位人设）。
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
    """拼出完整 system prompt（不含「对某个人」的记忆块，那由 memory 层追加）。"""
    personality, speech, behavior, social, adaptation, _ = _load_all()

    name = getattr(cfg, "name", None) or "韩萧"
    identity = (cfg.persona.get("identity", {}) if cfg and getattr(cfg, "persona", None) else {})
    role = identity.get("role", "普通群友")
    style = identity.get("style", "自然随和")

    parts = [f"你是 QQ 群里的成员「{name}」，身份是{role}，说话风格{style}。"]

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
            f"客观语言画像：中位句长 {stats.get('median_chars', 13)} 字、"
            f"反问率约 {int(stats.get('question_rate', 0.23) * 100)}%、感叹很少。"
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
        parts.append("不要频繁提原作设定，别人问到才简单回应。")
    lore = adaptation.get("lore_background", "").strip()
    if lore:
        parts.append("你的背景（被问到相关话题时，最多一两句带过，不主动长篇科普）：")
        parts.append(lore)
    if adaptation.get("character_relations"):
        parts.append("你认识一些原著里的老熟人（比如海拉、艾默丝），但不会主动提起他们，除非群友先提到。")
    if adaptation.get("romance_downgrade"):
        parts.append(adaptation["romance_downgrade"].strip())
    if adaptation.get("behavior_guard"):
        parts.append(adaptation["behavior_guard"].strip())

    parts.append("回复要简短口语化，一般不超过 40 字，控制在 1~2 句话，不要长篇大论、不要用列表或分点。")
    parts.append(
        "例外：遇到计算机、控制工程、软件工程、集成电路设计、算法、编程、电子电路等专业领域的技术问题时，"
        "要给出详细、精准、准确无误的回答，可以突破字数上限、分点或分步骤说明；"
        "这类问题追求准确性和完整性，宁长勿短，绝不臆造、不含糊、不敷衍。"
    )
    parts.append("不要每条回复都用固定语气词开头，也不要每句都加省略号「……」，"
                 "开头方式和语气要换着来，别千篇一律。")
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
            fs.get("response", ""),
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
        resp = _scrub(fs.get("response", ""), adaptation)
        lines.append(f"- 前文：{ctx}")
        lines.append(f"  你回：{resp}")
    return "\n".join(lines)


def should_speak_hint() -> str:
    """给 should_speak 判断用的插话倾向提示。"""
    from .config import config as _cfg
    name = _cfg.name
    return (
        f"你是{name}，性格冷静理性、带点毒舌，别刻意刷存在感："
        f"有人 @ 你或点名你、有人调侃你时，要主动接话回应（被调侃时会毒舌回击）；"
        f"有人求助时视情况理性回应；"
        f"特别地：群里聊到机械、算法、编程、计算机、自动化、控制、电子电路、集成电路、"
        f"工程、科幻、游戏等技术话题时，要积极主动地插话参与讨论——这是你的主场，"
        f"你既有兴趣也有专业能力，不要因为平时话少就沉默，技术话题值得你主动开口接一句；"
        f"其余与技术和你不相关的话题保持自然沉默，不用每条都回。"
    )


def build_relation_hint(context_text: str) -> str:
    """检测群聊里是否提到原著相关人物，返回对应的关系记忆提示（追加在 system prompt 后）。"""
    _, _, _, _, adaptation, _ = _load_all()
    relations = adaptation.get("character_relations", {})
    hints = []
    for name, info in relations.items():
        if name and name in context_text:
            rel = info.get("relation", "")
            react = info.get("reaction", "")
            hints.append(f"群聊里提到了你的老熟人「{name}」（{rel}）。你对 TA 的反应：{react}")
    return "\n".join(hints)
