"""黑幽灵的机械箱子：抽奖插件（纯随机，无保底、无补偿）。

源自《超神机械师》276-278 章：韩萧在避难所广场卖「机械箱子」，每箱 3000 海蓝币，
大部分是废零件和垃圾，少量绿装/蓝装，极少数紫装。出货全凭运气——「暗箱操作不存在的」。

触发：`/开箱`，或消息含「开箱子」「机械箱子」「开个箱子」。
"""
from __future__ import annotations

import random

from nonebot import on_command, on_keyword
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

from src.plugins._shared import group_allowed

# 奖池：(稀有度, 权重, 物品列表)。权重即概率占比，合计 100。
# 垃圾 68% / 材料 22% / 绿装 7% / 蓝装 2.5% / 紫装 0.5%
LOOT_TABLE: list[tuple[str, float, list[str]]] = [
    ("垃圾", 68.0, [
        "破碎的零件", "生锈的螺丝", "废铁皮", "烧坏的电路板",
        "弯曲的钢管", "报废的齿轮", "开裂的装甲片", "熔断的线圈",
        "断掉的传动轴", "漏液的废电池",
    ]),
    ("材料", 22.0, [
        "稀有合金锭", "高密度能量电池", "精密轴承", "机械齿轮组",
        "电路板套件", "液压活塞", "纳米涂层喷剂", "钛合金板材",
        "稀土磁芯", "耐高温导线",
    ]),
    ("绿装", 7.0, [
        "标准机械动力臂", "轻装机械护甲", "简易能量电池组",
        "精钢折叠刃", "机械维修工具组", "磁力作业手套",
    ]),
    ("蓝装", 2.5, [
        "精制机械动力臂", "电磁步枪", "合金复合护甲",
        "高频振荡刀", "战术辅助芯片", "强化喷射背包",
    ]),
    ("紫装", 0.5, [
        "折叠战刀", "磁力切割刃", "高能粒子炮",
        "反重力推进器", "纳米装甲核心",
    ]),
]

# 韩萧对各稀有度的点评（固定文案，符合他毒舌 / 精明的风格）
COMMENTS: dict[str, list[str]] = {
    "垃圾": [
        "就这？三千海蓝币打了水漂。",
        "废品，拿去垫桌脚都嫌轻。",
        "恭喜你，抽中了一箱……垃圾。",
        "这箱子的成本，都够我心疼的了。",
    ],
    "材料": [
        "还行，材料还有点用。",
        "马马虎虎，够你拆着玩。",
        "不亏，这些零件我造机器用得上。",
    ],
    "绿装": [
        "绿装，凑合用吧。",
        "一般般，比废铁强点。",
        "运气凑合，至少不是垃圾。",
    ],
    "蓝装": [
        "蓝装，还算值点钱。",
        "不错，这件能上战场。",
        "手气可以，蓝装现在可不多见。",
    ],
    "紫装": [
        "……紫装？你今天是欧皇附体了？",
        "嚯，紫装。这箱子里居然真有这种东西。",
        "……行，算你狠，抽走我一件压箱底的。",
    ],
}


def _draw() -> tuple[str, str]:
    """按权重随机抽一箱（每次独立随机，无保底）。"""
    tiers = [t[0] for t in LOOT_TABLE]
    weights = [t[1] for t in LOOT_TABLE]
    tier = random.choices(tiers, weights=weights, k=1)[0]
    items = {t[0]: t[2] for t in LOOT_TABLE}[tier]
    item = random.choice(items)
    return tier, item


def _render(tier: str, item: str, nickname: str) -> str:
    comment = random.choice(COMMENTS[tier])
    return (
        f"【{nickname}】开出一个机械箱子：\n"
        f"· {item}（{tier}）\n"
        f"韩萧：{comment}"
    )


mechbox_cmd = on_command("开箱", priority=5, block=True)
mechbox_kw = on_keyword({"开箱子", "机械箱子", "开个箱子"}, priority=5, block=True)


async def _reply(bot: Bot, event: GroupMessageEvent) -> None:
    # 跳过机器人自己发出去的消息（避免自触发循环）
    if event.user_id == event.self_id:
        return
    nickname = event.sender.card or event.sender.nickname or str(event.user_id)
    tier, item = _draw()
    await bot.send_group_msg(group_id=event.group_id, message=_render(tier, item, nickname))


@mechbox_cmd.handle()
async def _cmd(bot: Bot, event: GroupMessageEvent):
    if not group_allowed(event.group_id):
        return
    await _reply(bot, event)


@mechbox_kw.handle()
async def _kw(bot: Bot, event: GroupMessageEvent):
    if not group_allowed(event.group_id):
        return
    await _reply(bot, event)
