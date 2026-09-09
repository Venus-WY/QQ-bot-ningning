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

# 奖池：(稀有度, 权重, 物品列表)。
LOOT_TABLE: list[tuple[str, float, list[str]]] = [
    ("垃圾", 70.0, [
        "破碎的零件", "生锈的螺丝", "废铁皮", "烧坏的电路板",
        "弯曲的钢管", "报废的齿轮", "开裂的装甲片", "熔断的线圈",
        "断掉的传动轴", "漏液的废电池",
    ]),
    ("材料", 20.0, [
        "稀有合金锭", "高密度能量电池", "精密轴承", "机械齿轮组",
        "电路板套件", "液压活塞", "纳米涂层喷剂", "钛合金板材",
        "稀土磁芯", "耐高温导线",
    ]),
    ("MC？", 0.5, [
        "下界合金锄", "安山岩", "花岗岩", "闪长岩",
        "钻石剑", "涂蜡的含水斑驳切制铜台阶", "竖半砖？", "下界合金升级锻造模板",
        "僵尸村民刷怪蛋", "喷溅型治疗药水",
    ]),
    ("杀戮尖塔？", 0.5, [
        "草莓", "故障机器人的废弃零件", "盛碗虫精灵球", "化学物X",
        "宾邦", "火龙果", "【愤怒】", "【回响斩击】",
        "皮草大衣", "【凡庸】",
    ]),
    ("绿装", 6.0, [
        "标准机械动力臂", "轻装机械护甲", "简易能量电池组",
        "精钢折叠刃", "机械维修工具组", "磁力作业手套",
    ]),
    ("蓝装", 3.0, [
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

COMMENTS2: list[str] = [
    "呵呵",
    "...",
    "童叟无欺",
    "箱子里面什么都可能有",
]

COMMENTSDEC: list[str] = [
    "十连抽可没有保底",
    "收获颇丰哈",
    "童叟无欺",
    "（嘟囔）真是头大肥羊",
]

COMMENTSP: dict[str, str] = {
    "竖半砖？" : "问了吗？……见鬼，真把这个加进来了？",
    "下界合金锄" : "终极奉献？",
    "盛碗虫精灵球": "去吧，安爹！",
    "化学物X": "那就站个未来吧",
    "【回响斩击】": "教科书般的【回响斩击】！",
}


def _draw(number: int = 1) -> list[tuple[str, str]]:
    """按权重随机抽 number 箱（每次独立随机，无保底）。"""
    tiers = [t[0] for t in LOOT_TABLE]                     # 所有稀有度名称
    weights = [t[1] for t in LOOT_TABLE]                   # 对应权重
    tier_items = {t[0]: t[2] for t in LOOT_TABLE}          # 稀有度 → 物品列表映射

    # 一次抽取 number 个稀有度（每个独立随机）
    chosen_tiers = random.choices(tiers, weights=weights, k=number)

    # 为每个稀有度随机选一个具体物品
    results = [(tier, random.choice({t[0]: t[2] for t in LOOT_TABLE}[tier])) for tier in chosen_tiers]
    return results


def _render(tier: str, item: str, nickname: str) -> str:
    if COMMENTSP.get(item):
        comment = COMMENTSP.get(item)
    elif random.random()>0.5:
        comment = random.choice(COMMENTS.get(tier, COMMENTS2))
    else: 
        comment = random.choice(COMMENTS2)
    return (
        f"【{nickname}】开出一个机械箱子：\n"
        f"· {item}({tier})\n"
        f"韩萧：{comment}"
    )

def _renderdec(tiers: list[str], items: list[str], nickname: str) -> str:
    comments = []
    for item in items:
        if COMMENTSP.get(item):
            comments.append(COMMENTSP.get(item))
    if not comments:
        comment = random.choice(COMMENTSDEC)
    else: 
        comment = random.choice(comments)
    result = f"【{nickname}】开出十个机械箱子：\n"
    return (
        f"【{nickname}】开出十个机械箱子：\n" +
        f"".join(f"· {item}({tier})\n" for (item,tier) in list(zip(items,tiers))) +
        f"韩萧：{comment}"
    )

        
mechbox_dec = on_command("十连", priority=5, block=True)
mechbox_cmd = on_command("开箱", priority=5, block=True)
mechbox_kw = on_keyword({"开箱子", "机械箱子", "开个箱子"}, priority=5, block=True)


async def _reply(bot: Bot, event: GroupMessageEvent) -> None:
    # 跳过机器人自己发出去的消息（避免自触发循环）
    if event.user_id == event.self_id:
        return
    nickname = event.sender.card or event.sender.nickname or str(event.user_id)
    result = _draw()
    tier, item = result[0]
    await bot.send_group_msg(group_id=event.group_id, message=_render(tier, item, nickname))

async def _replydec(bot: Bot, event: GroupMessageEvent) -> None:
    # 跳过机器人自己发出去的消息（避免自触发循环）
    if event.user_id == event.self_id:
        return
    nickname = event.sender.card or event.sender.nickname or str(event.user_id)
    result = _draw(10)
    tiers:list[str] = []
    items:list[str] = []
    for ob in result:
        tier, item = ob
        tiers.append(tier)
        items.append(item)
    await bot.send_group_msg(group_id=event.group_id, message=_renderdec(tiers, items, nickname))


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

@mechbox_dec.handle()
async def _dec(bot: Bot, event: GroupMessageEvent):
    if not group_allowed(event.group_id):
        return
    await _replydec(bot, event)