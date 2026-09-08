"""今日老婆插件：随机抽一张二次元图 + 角色名 + 韩萧点评。

与 fortune（今日运势）的区别：**不锁日期**，每次触发都重新随机，可能抽到不同结果。
图库复用 _shared/image_pool（图片名即角色名），新增图即时生效（_scan 每次现扫目录，无缓存）。

触发：`/老婆` 命令，或消息含「今日老婆」「来点美图」「来张美图」。
（「/今日老婆」「/来点美图」这类带斜杠的写法，纯文本里仍含关键词，由 on_keyword 兜底触发，不与 /老婆 命令重叠。）
"""
from __future__ import annotations

from nonebot import logger, on_command, on_keyword
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment

from src.plugins._shared import chat, get_random_image, group_allowed

waifu_cmd = on_command("老婆", priority=5, block=True)
waifu_kw = on_keyword({"今日老婆", "来点美图", "来张美图"}, priority=5, block=True)


async def _reply(bot: Bot, event: GroupMessageEvent) -> None:
    # 跳过机器人自己发出去的消息（避免自我触发循环）
    if event.user_id == event.self_id:
        return

    nickname = event.sender.card or event.sender.nickname or str(event.user_id)
    img = get_random_image()  # 不传种子 → 每次随机，多次询问可抽到不同结果

    if img is None:
        await bot.send_group_msg(group_id=event.group_id, message="（图库还是空的，先去放几张图吧～）")
        return

    msg = Message()
    # 用 base64 发送（bytes → base64://），不依赖本地路径格式/编码，最稳
    msg += MessageSegment.image(file=img.path.read_bytes())
    msg += f"【{nickname}】今天的缘分是：{img.character}"

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
                    "content": f"群友今天随机抽到角色「{img.character}」（作品《{img.series}》）。"
                    f"用一句话点评一下这位角色。",
                },
            ],
            max_tokens=60,
        )
        if comment:
            msg += f"\n韩萧：{comment}"
    except Exception as exc:
        logger.warning(f"[今日老婆] 点评生成失败：{exc}")

    try:
        await bot.send_group_msg(group_id=event.group_id, message=msg)
    except Exception as exc:
        logger.error(f"[今日老婆] 发送失败：{exc}")


@waifu_cmd.handle()
async def _cmd(bot: Bot, event: GroupMessageEvent):
    if not group_allowed(event.group_id):
        return
    await _reply(bot, event)


@waifu_kw.handle()
async def _kw(bot: Bot, event: GroupMessageEvent):
    if not group_allowed(event.group_id):
        return
    await _reply(bot, event)
