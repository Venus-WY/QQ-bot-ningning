"""关系数值：熟悉度 / 好感度 / 信任度 / 被调侃耐受度。

设计原则：
  - 熟悉度 ≠ 好感度：聊得多不等于喜欢（familiarity=90 / affection=15 是合理的）。
  - 事件驱动增减，不做「说一句 +1」这种能被刷的规则。
  - 全部 clamp 到 [-100, 100]；只有熟悉度会缓慢衰减，好感/信任基本不掉。
  - 关系数值只影响「怎么对这个人说话」，永不修改核心人格（persona 只允许手动更新）。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, fields

LO, HI = -100.0, 100.0

# 数值默认值（没有记录时）
DEFAULTS = {
    "familiarity": 0.0,
    "affection": 0.0,
    "trust": 0.0,
    "teasing_tolerance": 30.0,
}


def _clamp(v: float) -> float:
    return max(LO, min(HI, float(v)))


@dataclass
class Relationship:
    familiarity: float = 0.0        # 熟悉度
    affection: float = 0.0          # 好感度
    trust: float = 0.0              # 信任度
    teasing_tolerance: float = 30.0  # 被调侃耐受度（默认能开点玩笑）

    def apply(self, d: "Relationship") -> "Relationship":
        """叠加一组增量（就地，返回 self 便于链式）。"""
        for f in fields(self):
            setattr(self, f.name, _clamp(getattr(self, f.name) + getattr(d, f.name)))
        return self

    def decay(self, factor: float = 1.0) -> "Relationship":
        """时间衰减：只掉熟悉度，好感/信任/耐受不掉。"""
        self.familiarity = _clamp(self.familiarity - factor)
        return self

    def to_dict(self) -> dict[str, float]:
        return {f.name: round(getattr(self, f.name), 1) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "Relationship":
        return cls(**{k: float(d.get(k, DEFAULTS[k])) for k in DEFAULTS})


def tone_hint(rel: "Relationship") -> str:
    """把关系数值翻译成一句「怎么说话」的规则，喂给模型。

    用熟悉度决定「熟不熟」，用好感度决定「喜不喜欢」，二者独立。
    """
    fam = rel.familiarity
    aff = rel.affection

    if fam < 10:
        fam_hint = "你们还不太熟，保持礼貌、不过分亲昵"
    elif fam < 40:
        fam_hint = "一般认识，可以稍微放松，不用太拘谨"
    elif fam < 70:
        fam_hint = "比较熟了，可以自然地开玩笑、吐槽"
    else:
        fam_hint = "很熟，可以随意一点，说话有默契"

    if aff < -30:
        aff_hint = "你对这个人有点抵触，语气偏冷淡"
    elif aff < 20:
        aff_hint = "对他没有特别的喜恶，平常心"
    elif aff < 60:
        aff_hint = "对他印象不错，会多一点关心"
    else:
        aff_hint = "你挺喜欢和这个人聊天，语气会更温柔亲切"

    return f"{fam_hint}；{aff_hint}。"
