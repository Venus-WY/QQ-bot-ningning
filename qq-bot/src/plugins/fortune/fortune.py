"""今日运势纯逻辑：读 fortunes.yaml，按分数分档（可单独测试）。"""
from __future__ import annotations

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
FORTUNES_PATH = HERE / "fortunes.yaml"


def load_fortunes() -> list[dict]:
    """读分档表，按 score_min 降序返回（保证从高分档往低匹配）。"""
    with open(FORTUNES_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    return sorted(raw, key=lambda x: int(x.get("score_min", 0)), reverse=True)


def pick_fortune(rng) -> dict:
    """用给定的 rng 抽一次运势，返回 {level, score, text}。

    rng 必须是 stable 种子（random.Random(f"{user_id}-{date}")），
    不能用内置 hash()——它每次进程重启都会变。
    """
    score = rng.randint(0, 100)
    for level in load_fortunes():
        if score >= int(level.get("score_min", 0)):
            texts = level.get("texts") or [""]
            return {
                "level": str(level.get("level", "吉")),
                "score": score,
                "text": rng.choice(texts),
            }
    return {"level": "大凶", "score": score, "text": ""}
