"""今日运势插件：同人同天结果固定，发二次元图片 + 运势 + 韩萧点评。

触发：`/运势` 或消息含「今日运势」。
确定性：用 random.Random(f"{user_id}-{date}") 做种子（不用 hash()，跨重启稳定）。
"""
from __future__ import annotations

import random
from datetime import date

from nonebot import logger, on_command, on_keyword
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment

from src.plugins._shared import chat, get_random_image, group_allowed
from .fortune import pick_fortune

fortune_cmd = on_command("运势", priority=5, block=True)
fortune_kw = on_keyword({"今日运势"}, priority=5, block=True)


async def _reply(bot: Bot, event: GroupMessageEvent) -> None:
    # 跳过机器人自己发出去的消息：运势文案里含「今日运势」四个字，
    # 若不跳过，机器人自己的回复会再次命中 on_keyword 形成自触发循环。
    if event.user_id == event.self_id:
        return

    user_id = event.user_id
    nickname = event.sender.card or event.sender.nickname or str(user_id)
    rng = random.Random(f"{user_id}-{date.today().isoformat()}")

    fortune = pick_fortune(rng)
    img = get_random_image(rng)

    msg = Message()
    if img is not None:
        # 用 base64 发送：不依赖本地路径格式/编码（Windows 反斜杠+中文路径会破坏 CQ 码），
        # NoneBot2 会把 bytes 转成 base64://，NapCat 解码后直接上传，最稳。
        msg += MessageSegment.image(file=img.path.read_bytes())
    msg += f"【{nickname}】今日运势：{fortune['level']}（{fortune['score']}分）\n{fortune['text']}"

    # 韩萧点评（可选，失败不阻塞发图）
    try:
        comment = await chat(
            [
                {
                    "role": "system",
                    "content": "你是 QQ 群里的韩萧，冷静理性、带点毒舌，说话简短。"
                    "不要堆砌语气词，不要每句都加省略号。",
                },
                {
                    "role": "user",
                    "content": f"群友今天抽到「{fortune['level']}」（{fortune['score']}分），"
                    f"运势文案是「{fortune['text']}」。用一句话点评一下。",
                },
            ],
            max_tokens=60,
        )
        if comment:
            msg += f"\n韩萧：{comment}"
    except Exception as exc:
        logger.warning(f"[运势] 点评生成失败：{exc}")

    try:
        await bot.send_group_msg(group_id=event.group_id, message=msg)
    except Exception as exc:
        logger.error(f"[运势] 发送失败：{exc}")


@fortune_cmd.handle()
async def _cmd(bot: Bot, event: GroupMessageEvent):
    if not group_allowed(event.group_id):
        return
    await _reply(bot, event)


@fortune_kw.handle()
async def _kw(bot: Bot, event: GroupMessageEvent):
    if not group_allowed(event.group_id):
        return
    await _reply(bot, event)
