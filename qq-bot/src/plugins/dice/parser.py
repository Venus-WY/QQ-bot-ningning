"""骰子表达式解析与掷骰（纯 Python，不依赖 nonebot，可单独测试）。

支持语法:
    rXdY           X 颗 Y 面骰（X 省略 = 1）
    rXdY±Z         常量修正
    rXdY±WdV       多组骰子
    rXdYkhN/klN    保留最大的 N 颗 / 最小的 N 颗（N 省略 = 1）
"""
import random
import re
from dataclasses import dataclass

MAX_DICE = 1000      # 单组骰子颗数上限
MAX_SIDES = 100    # 面数上限
MAX_TERMS = 10      # 单条表达式组数上限

_DICE_RE = re.compile(r"^\s*(\d+)?\s*[dD]\s*(\d+)\s*(?:([kK][hH]|[kK][lL])\s*(\d+)?)?")
_CONST_RE = re.compile(r"^\s*(\d+)\s*")
_SIGN_RE = re.compile(r"^\s*([+-])")


class DiceError(Exception):
    """骰子表达式解析或校验失败。"""


@dataclass
class RollResult:
    expr: str      # 规范化后的表达式，如 "2d8 + 1"
    detail: str    # 掷骰明细，如 "3 + 7 + 1"；被弃骰子以 "(x)" 标出
    total: int     # 最终结果


def _keep_suffix(keep_hi, keep):
    if keep_hi is None:
        return ""
    return ("kh" if keep_hi else "kl") + str(keep)


def _rolls_str(kept, dropped):
    s = " + ".join(str(x) for x in kept)
    if dropped:
        s += " + (" + ", ".join(str(x) for x in dropped) + ")"
    return s


def roll_expr(text: str) -> RollResult:
    """解析骰子表达式并掷骰。解析或校验失败抛 DiceError。"""
    s = text.strip()
    if s.startswith("/"):
        s = s[1:].lstrip()
    if not s or s[0] not in "rR":
        raise DiceError(f"无法解析：{text}，骰子表达式应以 r 开头")
    s = s[1:]

    terms = []  # ("dice", sign, count, sides, keep_hi, keep) 或 ("const", sign, value)
    dice_count = 0
    first = True
    while s.strip():
        sign = 1
        if not first:
            m = _SIGN_RE.match(s)
            if not m:
                raise DiceError(f"无法解析：{text}")
            sign = -1 if m.group(1) == "-" else 1
            s = s[m.end():]
        dm = _DICE_RE.match(s)
        if dm:
            count = int(dm.group(1)) if dm.group(1) else 1
            sides = int(dm.group(2))
            keep_hi = None
            keep = None
            if dm.group(3):
                keep_hi = dm.group(3).lower() == "kh"
                keep = int(dm.group(4)) if dm.group(4) else 1
            if count < 1:
                raise DiceError("骰子数需至少为 1")
            if count > MAX_DICE:
                raise DiceError(f"骰子数最多 {MAX_DICE} 颗")
            if sides < 1 or sides > MAX_SIDES:
                raise DiceError(f"面数需在 1~{MAX_SIDES} 之间")
            if keep is not None and not 1 <= keep <= count:
                raise DiceError(f"保留数需在 1~{count} 之间")
            terms.append(("dice", sign, count, sides, keep_hi, keep))
            dice_count += 1
            s = s[dm.end():]
        else:
            cm = _CONST_RE.match(s)
            if not cm:
                raise DiceError(f"无法解析：{text}")
            terms.append(("const", sign, int(cm.group(1))))
            s = s[cm.end():]
        first = False

    if dice_count == 0:
        raise DiceError("至少需要一个骰子，如 r1d6")
    if len(terms) > MAX_TERMS:
        raise DiceError(f"单次最多 {MAX_TERMS} 组")

    expr_parts = []
    detail_parts = []
    total = 0
    for i, term in enumerate(terms):
        op = "" if i == 0 else (" + " if term[1] > 0 else " - ")
        if term[0] == "const":
            val = term[2]
            total += term[1] * val
            expr_parts.append(f"{op}{val}")
            detail_parts.append(f"{op}{val}")
            continue
        _, sign, count, sides, keep_hi, keep = term
        rolls = [random.randint(1, sides) for _ in range(count)]
        if keep_hi is None:
            kept, dropped = rolls, []
        else:
            ordered = sorted(rolls, reverse=keep_hi)
            kept, dropped = ordered[:keep], ordered[keep:]
        total += sign * sum(kept)
        expr_parts.append(f"{op}{count}d{sides}{_keep_suffix(keep_hi, keep)}")
        detail = _rolls_str(kept, dropped)
        if sign < 0 and dropped:
            detail = f"({detail})"  # 减号下带被弃骰子时加括号，避免误读
        detail_parts.append(f"{op}{detail}")
    return RollResult(expr="".join(expr_parts), detail="".join(detail_parts), total=total)
