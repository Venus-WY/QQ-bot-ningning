"""骰子插件：群聊中识别 rXdY 等骰子表达式并回复结果。

示例:
    r1d6        ->  🎲 1d6 = 4
    r2d8+1      ->  🎲 2d8 + 1 = 3 + 7 + 1 = 11
    r4d6kh3     ->  🎲 4d6kh3 = 6 + 5 + 4 + (2) = 15
"""
import re

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.rule import regex as regex_rule

from src.plugins._shared import group_allowed
from .parser import DiceError, roll_expr

# 只拦截「看起来像骰子命令」的消息，其余照常流向低优先级插件（如核心 AI 群友）
DICE_PATTERN = re.compile(r"^/?r[0-9dkhkl+\- ]*$", re.IGNORECASE)

dice = on_message(rule=regex_rule(DICE_PATTERN), priority=5, block=True)


@dice.handle()
async def _(event: GroupMessageEvent):
    if not group_allowed(event.group_id):
        return
    try:
        result = roll_expr(event.get_plaintext().strip())
    except DiceError as exc:
        await dice.finish(f"🎲 {exc}\n用法：rXdY，如 r1d6 / r2d8+1 / r4d6kh3")
        return
    if result.detail == str(result.total):  # 单颗骰子无修正，简化显示
        msg = f"🎲 {result.expr} = {result.total}"
    else:
        msg = f"🎲 {result.expr} = {result.detail} = {result.total}"
    await dice.finish(msg)
